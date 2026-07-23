#!/usr/bin/env python3
"""Audit whether SparseDrive's real-source plan depends on RGB and ego status.

This is a receiver ablation, not a benchmark or a semantic-correctness test.
It holds the real source window, calibration, poses and command fixed while
removing spatial RGB information, freezing visual history, or perturbing only
the declared forward component of the 10-D ego-status vector.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np

from render_hugsim_exact_source_pose import select_camera_records
from run_sparse4d_hugsim_receiver import sha256_file
from run_sparsedrive_hugsim_receiver import (
    build_model,
    ensure_anchor_assets,
    source_provenance,
    validate_compatibility_patch,
)
from run_sparsedrive_real_source import (
    PLAN_STEP_SECONDS,
    PLAN_STEPS,
    RESET_TOLERANCE,
    clean_run_for_json,
    load_metadata,
    max_plan_difference,
    normalized_model_poses,
    run_sequence,
    validate_indices,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-report", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--runtime-deps", type=Path, required=True)
    parser.add_argument("--anchor-dir", type=Path, required=True)
    parser.add_argument("--ego-speed-delta-mps", type=float, default=2.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        result = json.load(stream)
    if not isinstance(result, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return result


def require_sha256(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    observed = sha256_file(path)
    if observed != expected:
        raise ValueError(
            f"{path}: SHA-256 mismatch; expected {expected}, observed {observed}"
        )


def warmed_plan_effect(
    baseline: dict[str, Any],
    condition: dict[str, Any],
) -> dict[str, Any]:
    base_frame = baseline["frames"][-1]
    condition_frame = condition["frames"][-1]
    base = np.asarray(base_frame["_final_plan"], dtype=np.float64)
    changed = np.asarray(condition_frame["_final_plan"], dtype=np.float64)
    if base.shape != (PLAN_STEPS, 2) or changed.shape != base.shape:
        raise ValueError("native plans must both have shape 6x2")
    delta = changed - base
    l2 = np.linalg.norm(delta, axis=1)
    return {
        "plan_ade_from_baseline_m": float(np.mean(l2)),
        "plan_endpoint_difference_m": float(l2[-1]),
        "max_abs_coordinate_difference_m": float(np.max(np.abs(delta))),
        "final_right_delta_m": float(delta[-1, 0]),
        "final_forward_delta_m": float(delta[-1, 1]),
        "baseline_final_xy_m": base[-1].astype(float).tolist(),
        "condition_final_xy_m": changed[-1].astype(float).tolist(),
        "baseline_mode": int(
            base_frame["planning_selection"]["selected_mode_index"]
        ),
        "condition_mode": int(
            condition_frame["planning_selection"]["selected_mode_index"]
        ),
    }


def constant_velocity_reference(status: list[float]) -> np.ndarray:
    vector = np.asarray(status, dtype=np.float64)
    if vector.shape != (10,) or not np.isfinite(vector).all():
        raise ValueError("expected one finite 10-D ego-status vector")
    times = PLAN_STEP_SECONDS * np.arange(1, PLAN_STEPS + 1, dtype=np.float64)
    return np.column_stack((vector[6] * times, vector[7] * times))


def plan_ade(plan: np.ndarray, reference: np.ndarray) -> float:
    plan = np.asarray(plan, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if plan.shape != (PLAN_STEPS, 2) or reference.shape != plan.shape:
        raise ValueError("plan and reference must both have shape 6x2")
    return float(np.mean(np.linalg.norm(plan - reference, axis=1)))


def run_named_condition(
    *,
    name: str,
    variant: str,
    ego_offset_mps: float,
    common: dict[str, Any],
) -> dict[str, Any]:
    result = run_sequence(
        variant=variant,
        ego_forward_velocity_offset_mps=ego_offset_mps,
        **common,
    )
    result["variant"] = name
    return result


def save_visualization(
    runs: dict[str, dict[str, Any]],
    effects: dict[str, dict[str, Any]],
    warmed_plan_ade_threshold_m: float,
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(15, 9), constrained_layout=True)
    grid = figure.add_gridspec(2, 3, height_ratios=(0.85, 1.15))

    image_rows = (
        ("baseline", "Real RGB"),
        ("rgb_center", "Constant normalization-centre RGB"),
        ("rgb_frozen", "First RGB frame repeated"),
    )
    for column, (name, title) in enumerate(image_rows):
        axis = figure.add_subplot(grid[0, column])
        axis.imshow(runs[name]["frames"][-1]["_raw_front"])
        axis.set_title(title)
        axis.axis("off")

    trajectory_axis = figure.add_subplot(grid[1, :2])
    baseline_frame = runs["baseline"]["frames"][-1]
    trajectory_axis.plot(
        baseline_frame["_reference"][:, 0],
        baseline_frame["_reference"][:, 1],
        marker="o",
        linewidth=2.5,
        color="#2ca02c",
        label="recorded motion",
    )
    colors = {
        "baseline": "#111111",
        "rgb_center": "#d62728",
        "rgb_frozen": "#ff7f0e",
        "ego_speed_minus": "#1f77b4",
        "ego_speed_plus": "#9467bd",
        "ego_pose_frozen": "#17becf",
    }
    labels = {
        "baseline": "baseline",
        "rgb_center": "constant RGB",
        "rgb_frozen": "frozen RGB history",
        "ego_speed_minus": "ego forward speed -2 m/s",
        "ego_speed_plus": "ego forward speed +2 m/s",
        "ego_pose_frozen": "frozen ego-pose history",
    }
    for name in labels:
        plan = runs[name]["frames"][-1]["_final_plan"]
        trajectory_axis.plot(
            plan[:, 0],
            plan[:, 1],
            marker="o",
            linewidth=2.0,
            color=colors[name],
            label=labels[name],
        )
    trajectory_axis.scatter([0], [0], marker="x", color="black")
    trajectory_axis.set(
        title="Fully warmed native 3 s plans",
        xlabel="right (+) / left (-), metres",
        ylabel="forward, metres",
    )
    trajectory_axis.grid(alpha=0.3)
    trajectory_axis.legend(fontsize=8)

    effect_axis = figure.add_subplot(grid[1, 2])
    names = list(effects)
    values = [effects[name]["plan_ade_from_baseline_m"] for name in names]
    effect_axis.bar(
        [labels[name] for name in names],
        values,
        color=[colors[name] for name in names],
    )
    effect_axis.axhline(
        warmed_plan_ade_threshold_m,
        color="black",
        linestyle="--",
        linewidth=1,
        label="warmed repeat + tolerance",
    )
    effect_axis.set(
        title="Plan change from baseline",
        ylabel="warmed-plan ADE, metres",
    )
    effect_axis.tick_params(axis="x", rotation=25)
    effect_axis.grid(axis="y", alpha=0.25)
    effect_axis.legend(fontsize=8)

    figure.suptitle(
        "SparseDrive visual-necessity and ego-status ablation\n"
        "(sensitivity evidence; not semantic correctness)",
        fontsize=15,
    )
    path = output / "sparsedrive_visual_necessity.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    qualification_path = args.qualification_report.expanduser().resolve()
    preregistration_path = args.preregistration.expanduser().resolve()
    runtime_deps = args.runtime_deps.expanduser().resolve()
    anchor_dir = args.anchor_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    speed_delta = float(args.ego_speed_delta_mps)

    if not math.isfinite(speed_delta) or speed_delta <= 0:
        raise ValueError("--ego-speed-delta-mps must be finite and positive")
    if not runtime_deps.is_dir():
        raise FileNotFoundError(runtime_deps)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")

    qualification = load_json(qualification_path)
    preregistration = load_json(preregistration_path)
    audit_id = preregistration.get("audit_id")
    if audit_id not in {
        "sparsedrive_visual_necessity_001",
        "sparsedrive_visual_necessity_002",
    }:
        raise ValueError("unexpected preregistration audit_id")
    registered_delta = float(
        preregistration["interventions"]["ego_forward_velocity"]["delta_mps"]
    )
    if speed_delta != registered_delta:
        raise ValueError(
            f"speed delta {speed_delta} differs from preregistered {registered_delta}"
        )

    source_info = qualification["source"]
    calibration_info = qualification["calibration"]
    model_info = qualification["model"]
    source_root = Path(source_info["root"]).expanduser().resolve()
    metadata_path = Path(source_info["metadata"]).expanduser().resolve()
    source_manifest = Path(source_info["archive_manifest"]).expanduser().resolve()
    metadata_manifest = Path(
        source_info["metadata_archive_manifest"]
    ).expanduser().resolve()
    calibration_run = Path(
        calibration_info["reference_run"]
    ).expanduser().resolve()
    root = Path(qualification["receiver_source"]["root"]).expanduser().resolve()
    checkpoint = Path(model_info["checkpoint"]).expanduser().resolve()
    frame_indices = [int(value) for value in source_info["frame_indices"]]
    stride = validate_indices(frame_indices)

    for path in (source_root, calibration_run, root):
        if not path.is_dir():
            raise FileNotFoundError(path)
    require_sha256(metadata_path, source_info["metadata_sha256"])
    require_sha256(source_manifest, source_info["archive_manifest_sha256"])
    require_sha256(
        metadata_manifest,
        source_info["metadata_archive_manifest_sha256"],
    )
    require_sha256(
        calibration_run / "infos.pkl",
        calibration_info["reference_infos_sha256"],
    )
    require_sha256(checkpoint, model_info["checkpoint_sha256"])
    current_source = source_provenance(root)
    for key in ("commit", "working_diff_sha256"):
        if current_source[key] != qualification["receiver_source"][key]:
            raise ValueError(f"SparseDrive source provenance changed at {key}")

    metadata = load_metadata(metadata_path)
    with (calibration_run / "infos.pkl").open("rb") as stream:
        calibration_infos = pickle.load(stream)
    front_l2c = np.asarray(
        calibration_infos[0]["cam_params"]["CAM_FRONT"]["l2c"],
        dtype=np.float64,
    )
    required_pose_indices: set[int] = set()
    for index in frame_indices:
        required_pose_indices.update((index - 2 * stride, index - stride, index))
        required_pose_indices.update(
            index + stride * step for step in range(1, PLAN_STEPS + 1)
        )
    poses = normalized_model_poses(
        metadata,
        sorted(required_pose_indices),
        front_l2c,
        normalization_index=frame_indices[0],
    )
    timestamp_gaps = []
    for previous, current in zip(
        frame_indices[:-1], frame_indices[1:], strict=True
    ):
        previous_time = float(
            select_camera_records(metadata, previous)["CAM_FRONT"]["timestamp"]
        )
        current_time = float(
            select_camera_records(metadata, current)["CAM_FRONT"]["timestamp"]
        )
        timestamp_gaps.append(current_time - previous_time)
    if max(abs(gap - PLAN_STEP_SECONDS) for gap in timestamp_gaps) > 0.02:
        raise ValueError(f"source interval is not approximately 2 Hz: {timestamp_gaps}")

    validate_compatibility_patch(root)
    sys.path.insert(0, str(runtime_deps))
    import torch

    anchor_paths = ensure_anchor_assets(checkpoint, anchor_dir, torch)
    model, torch, model_provenance = build_model(
        root,
        checkpoint,
        anchor_paths,
    )
    for key in ("checkpoint_sha256", "config_sha256"):
        if model_provenance[key] != model_info[key]:
            raise ValueError(f"model provenance changed at {key}")

    output.mkdir(parents=True)
    common = {
        "source_root": source_root,
        "metadata": metadata,
        "frame_indices": frame_indices,
        "stride": stride,
        "poses": poses,
        "front_l2c": front_l2c,
        "model": model,
        "torch": torch,
        "front_intrinsic_shift_px": 80.0,
    }
    conditions = (
        ("baseline", "baseline", 0.0),
        ("baseline_repeat", "baseline", 0.0),
        ("rgb_center", "normalization_center_rgb", 0.0),
        ("rgb_frozen", "temporal_freeze_first", 0.0),
        ("ego_speed_minus", "baseline", -speed_delta),
        ("ego_speed_plus", "baseline", speed_delta),
        ("ego_pose_frozen", "ego_pose_history_frozen", 0.0),
    )
    runs = {
        name: run_named_condition(
            name=name,
            variant=variant,
            ego_offset_mps=offset,
            common=common,
        )
        for name, variant, offset in conditions
    }

    repeat_max_abs = max_plan_difference(
        runs["baseline"],
        runs["baseline_repeat"],
    )
    warmed_repeat_effect = warmed_plan_effect(
        runs["baseline"],
        runs["baseline_repeat"],
    )
    prior_native_path = Path(
        qualification["artifacts"]["native_outputs"]
    ).expanduser().resolve()
    require_sha256(
        prior_native_path,
        qualification["artifacts"]["native_outputs_sha256"],
    )
    prior_native = torch.load(prior_native_path, map_location="cpu")
    prior_difference = max_plan_difference(
        runs["baseline"],
        {"native_outputs": prior_native["baseline"]},
    )

    effects = {
        name: warmed_plan_effect(runs["baseline"], runs[name])
        for name in (
            "rgb_center",
            "rgb_frozen",
            "ego_speed_minus",
            "ego_speed_plus",
            "ego_pose_frozen",
        )
    }
    max_abs_effect_threshold = repeat_max_abs + RESET_TOLERANCE
    warmed_plan_ade_threshold = (
        warmed_repeat_effect["plan_ade_from_baseline_m"] + RESET_TOLERANCE
    )
    for name, effect in effects.items():
        effect["all_frame_max_abs_coordinate_difference_m"] = (
            max_plan_difference(runs["baseline"], runs[name])
        )
        effect["warmed_effect_exceeds_repeat_plus_tolerance"] = (
            effect["max_abs_coordinate_difference_m"] > max_abs_effect_threshold
        )
        frame = runs[name]["frames"][-1]
        motion_prior = constant_velocity_reference(
            frame["input_contract"]["ego_status_10d"]
        )
        effect["plan_ade_to_constant_velocity_prior_m"] = plan_ade(
            frame["_final_plan"],
            motion_prior,
        )
        effect["plan_non_degenerate"] = (
            float(np.linalg.norm(frame["_final_plan"][-1])) > 0.1
        )

    baseline_frame = runs["baseline"]["frames"][-1]
    baseline_prior = constant_velocity_reference(
        baseline_frame["input_contract"]["ego_status_10d"]
    )
    baseline_prior_ade = plan_ade(
        baseline_frame["_final_plan"],
        baseline_prior,
    )
    visual_influence = effects["rgb_center"][
        "warmed_effect_exceeds_repeat_plus_tolerance"
    ]
    visual_history_influence = effects["rgb_frozen"][
        "warmed_effect_exceeds_repeat_plus_tolerance"
    ]
    state_influence = all(
        effects[name]["warmed_effect_exceeds_repeat_plus_tolerance"]
        for name in ("ego_speed_minus", "ego_speed_plus")
    )
    pose_history_influence = effects["ego_pose_frozen"][
        "warmed_effect_exceeds_repeat_plus_tolerance"
    ]

    native_path = output / "native_outputs.pt"
    torch.save(
        {
            name: run["native_outputs"]
            for name, run in runs.items()
        },
        native_path,
    )
    visual_path = save_visualization(
        runs,
        effects,
        warmed_plan_ade_threshold,
        output,
    )
    report = {
        "audit_id": audit_id,
        "purpose": (
            "test whether the pinned SparseDrive plan causally depends on "
            "six-camera RGB and declared ego forward velocity on one real slice"
        ),
        "preregistration": {
            "path": str(preregistration_path),
            "sha256": sha256_file(preregistration_path),
        },
        "qualification_basis": {
            "path": str(qualification_path),
            "sha256": sha256_file(qualification_path),
            "prior_baseline_max_abs_difference_m": prior_difference,
        },
        "source": {
            "root": str(source_root),
            "metadata": str(metadata_path),
            "metadata_sha256": sha256_file(metadata_path),
            "frame_indices": frame_indices,
            "timestamp_gaps_s": timestamp_gaps,
        },
        "model": model_provenance,
        "receiver_source": current_source,
        "adapter": {
            "runner": str(Path(__file__).resolve()),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "real_source_helper": str(
                Path(run_sequence.__code__.co_filename).resolve()
            ),
            "real_source_helper_sha256": sha256_file(
                Path(run_sequence.__code__.co_filename).resolve()
            ),
        },
        "interventions": {
            "rgb_center": (
                "replace every camera pixel by rounded ImageNet normalization "
                "mean while preserving timestamps, calibration, poses, command "
                "and ego status"
            ),
            "rgb_frozen": (
                "repeat the first source RGB frame across four logical "
                "timestamps while preserving current timestamps, calibration, "
                "poses, command and ego status"
            ),
            "ego_speed_minus": (
                f"subtract {speed_delta:.3f} m/s only from ego_status[6]"
            ),
            "ego_speed_plus": (
                f"add {speed_delta:.3f} m/s only to ego_status[6]"
            ),
            "ego_pose_frozen": (
                "repeat the first source model-to-world pose in img_metas "
                "across all four frames while leaving RGB, status, projection "
                "matrices, timestamps and command unchanged"
            ),
        },
        "runs": {
            name: clean_run_for_json(run)
            for name, run in runs.items()
        },
        "measurement": {
            "repeat_max_abs_coordinate_difference_m": repeat_max_abs,
            "warmed_repeat_effect": warmed_repeat_effect,
            "repeat_tolerance_m": RESET_TOLERANCE,
            "max_abs_effect_threshold_m": max_abs_effect_threshold,
            "warmed_plan_ade_effect_threshold_m": warmed_plan_ade_threshold,
            "baseline_plan_ade_to_constant_velocity_prior_m": baseline_prior_ade,
            "effects": effects,
        },
        "decisions": {
            "overall": "down-weighted",
            "rgb_stream_causally_influences_plan_on_this_slice": (
                "accepted" if visual_influence else "down-weighted"
            ),
            "visual_history_causally_influences_plan_on_this_slice": (
                "accepted" if visual_history_influence else "down-weighted"
            ),
            "declared_ego_forward_velocity_causally_influences_plan_on_this_slice": (
                "accepted" if state_influence else "down-weighted"
            ),
            "declared_ego_pose_history_causally_influences_plan_on_this_slice": (
                "accepted" if pose_history_influence else "down-weighted"
            ),
            "sparsedrive_completely_ignores_rgb_on_this_slice": (
                "rejected" if visual_influence else "down-weighted"
            ),
            "sparsedrive_uses_correct_task_semantics_without_shortcuts": "rejected",
            "effect_magnitude_establishes_visual_vs_state_dominance": "rejected",
        },
        "claim_boundary": {
            "accepted": (
                "only causal sensitivity that exceeds paired numerical repeat "
                "plus the frozen local tolerance"
            ),
            "down_weighted": (
                "one near-straight four-frame real slice, a constant-RGB "
                "out-of-distribution ablation, a deliberately inconsistent "
                "frozen history and synthetic ego-status offsets"
            ),
            "rejected": [
                "visual sensitivity proves semantically correct perception",
                "a non-degenerate plan under removed RGB proves safe fallback",
                "the larger of two non-commensurate perturbation effects proves "
                "which input the model truly relies on",
                "this receiver ablation qualifies HUGSIM",
            ],
        },
        "artifacts": {
            "native_outputs": str(native_path),
            "native_outputs_sha256": sha256_file(native_path),
            "visualization": str(visual_path),
            "visualization_sha256": sha256_file(visual_path),
        },
    }
    report_path = output / "sparsedrive_visual_necessity.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
