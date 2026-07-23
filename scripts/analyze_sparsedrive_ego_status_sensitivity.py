#!/usr/bin/env python3
"""Compare two equally warmed SparseDrive ego-status constructions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_MODES = ("recorded_scalar", "pose_derived")
RESET_NUMERICAL_ENVELOPE = 1e-4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recorded-report", type=Path, required=True)
    parser.add_argument("--pose-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def only_condition(report: dict[str, Any], mode: str) -> dict[str, Any]:
    conditions = report.get("conditions", [])
    if len(conditions) != 1:
        raise ValueError(f"{mode}: expected exactly one condition")
    condition = conditions[0]
    if condition.get("ego_status_mode") != mode:
        raise ValueError(
            f"expected {mode}, got {condition.get('ego_status_mode')}"
        )
    if not report.get("all_outputs_finite"):
        raise ValueError(f"{mode}: non-finite native output")
    if not report.get("all_resets_reproducible"):
        raise ValueError(f"{mode}: reset check failed")
    return condition


def plan(frame: dict[str, Any]) -> np.ndarray:
    value = np.asarray(frame["native"]["final_planning_values"], dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 2:
        raise ValueError(f"unexpected plan shape: {value.shape}")
    return value


def analyze_reports(
    recorded: dict[str, Any],
    pose: dict[str, Any],
) -> dict[str, Any]:
    recorded_condition = only_condition(recorded, "recorded_scalar")
    pose_condition = only_condition(pose, "pose_derived")
    if recorded_condition["input"] != pose_condition["input"]:
        raise ValueError("status variants use different HUGSIM inputs")
    if (
        recorded_condition["selected_frame_indices"]
        != pose_condition["selected_frame_indices"]
    ):
        raise ValueError("status variants use different receiver frames")
    recorded_checkpoint = recorded["model"]["checkpoint_sha256"]
    pose_checkpoint = pose["model"]["checkpoint_sha256"]
    if recorded_checkpoint != pose_checkpoint:
        raise ValueError("status variants use different checkpoints")

    comparisons = []
    for recorded_frame, pose_frame in zip(
        recorded_condition["frames"],
        pose_condition["frames"],
        strict=True,
    ):
        if recorded_frame["frame_index"] != pose_frame["frame_index"]:
            raise ValueError("status variants have mismatched frame indices")
        recorded_plan = plan(recorded_frame)
        pose_plan = plan(pose_frame)
        waypoint_delta = np.linalg.norm(recorded_plan - pose_plan, axis=1)
        comparisons.append(
            {
                "frame_index": recorded_frame["frame_index"],
                "timestamp_s": recorded_frame["timestamp_s"],
                "recorded_scalar": {
                    "plan_geometry": recorded_frame["plan_geometry"],
                    "selected_mode_index": recorded_frame["planning_selection"][
                        "selected_mode_index"
                    ],
                },
                "pose_derived": {
                    "plan_geometry": pose_frame["plan_geometry"],
                    "selected_mode_index": pose_frame["planning_selection"][
                        "selected_mode_index"
                    ],
                },
                "first_step_speed_abs_delta_mps": abs(
                    recorded_frame["plan_geometry"]["first_step_speed_mps"]
                    - pose_frame["plan_geometry"]["first_step_speed_mps"]
                ),
                "final_endpoint_delta_m": float(waypoint_delta[-1]),
                "maximum_waypoint_delta_m": float(np.max(waypoint_delta)),
                "selected_mode_switch": bool(
                    recorded_frame["planning_selection"]["selected_mode_index"]
                    != pose_frame["planning_selection"]["selected_mode_index"]
                ),
            }
        )

    final = comparisons[-1]
    final_structural_stability = all(
        (
            final[mode]["plan_geometry"]["forward_monotonic_non_decreasing"]
            and final[mode]["plan_geometry"]["final_forward_m"] > 0.0
        )
        for mode in EXPECTED_MODES
    )
    maximum_plan_delta = max(
        frame["maximum_waypoint_delta_m"] for frame in comparisons
    )
    within_reset_envelope = maximum_plan_delta <= RESET_NUMERICAL_ENVELOPE
    return {
        "experiment": "sparsedrive_ego_status_sensitivity_001",
        "input": recorded_condition["input"],
        "checkpoint_sha256": recorded_checkpoint,
        "selected_frame_indices": recorded_condition["selected_frame_indices"],
        "comparison_scope": (
            "same HUGSIM RGB/calibration and SparseDrive checkpoint; "
            "independent reset and equal four-frame temporal warm-up"
        ),
        "status_vectors": {
            "recorded_scalar": [
                item["ego_status_10d"]
                for item in recorded_condition["input_contracts"]
            ],
            "pose_derived": [
                item["ego_status_10d"]
                for item in pose_condition["input_contracts"]
            ],
        },
        "frames": comparisons,
        "fully_warmed_frame": final,
        "maximum_plan_delta_across_all_frames_m": maximum_plan_delta,
        "reset_numerical_envelope": RESET_NUMERICAL_ENVELOPE,
        "within_reset_numerical_envelope": within_reset_envelope,
        "evidence_decisions": {
            "structural_baseline_stability": {
                "decision": (
                    "accepted" if final_structural_stability else "rejected"
                ),
                "claim": (
                    "both reasonable ego-status constructions preserve a "
                    "finite, positive, monotonically forward fully warmed plan"
                ),
            },
            "quantitative_plan_equivalence": {
                "decision": (
                    "accepted" if within_reset_envelope else "down-weighted"
                ),
                "reason": (
                    "the tested cross-construction plan difference is compared "
                    "only with the frozen reset reproducibility envelope; this "
                    "is an internal adapter claim, not an externally qualified "
                    "task-equivalence bound"
                ),
            },
            "receiver_or_hugsim_real_world_credibility": {
                "decision": "rejected",
                "reason": (
                    "one internal normal-scene sensitivity audit cannot "
                    "establish real-world task equivalence"
                ),
            },
        },
    }


def save_visualization(
    analysis: dict[str, Any],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    frames = analysis["frames"]
    final = frames[-1]
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)

    plan_axis = axes[0, 0]
    for mode, color in zip(EXPECTED_MODES, ("#1f77b4", "#ff7f0e"), strict=True):
        geometry = final[mode]["plan_geometry"]
        # The report stores geometry summaries; recover the final plan from the
        # per-frame endpoint series below for this compact qualification plot.
        endpoints = np.asarray(
            [
                [
                    frame[mode]["plan_geometry"]["final_right_m"],
                    frame[mode]["plan_geometry"]["final_forward_m"],
                ]
                for frame in frames
            ]
        )
        plan_axis.plot(
            endpoints[:, 0],
            endpoints[:, 1],
            marker="o",
            color=color,
            label=f"{mode}: receiver-frame endpoints",
        )
        plan_axis.scatter(
            [geometry["final_right_m"]],
            [geometry["final_forward_m"]],
            color=color,
            s=90,
        )
    plan_axis.set(
        title="Plan endpoints across equal warm-up",
        xlabel="right (+) / left (-), m",
        ylabel="forward, m",
    )
    plan_axis.grid(alpha=0.3)
    plan_axis.legend()

    status_axis = axes[0, 1]
    indices = np.arange(10)
    width = 0.38
    for offset, mode, color in zip(
        (-width / 2, width / 2),
        EXPECTED_MODES,
        ("#1f77b4", "#ff7f0e"),
        strict=True,
    ):
        status_axis.bar(
            indices + offset,
            analysis["status_vectors"][mode][-1],
            width=width,
            color=color,
            label=mode,
        )
    status_axis.set(
        title="Fully warmed 10-D ego status",
        xlabel="status component index",
        ylabel="input value",
        xticks=indices,
    )
    status_axis.grid(axis="y", alpha=0.3)
    status_axis.legend()

    timestamps = [frame["timestamp_s"] for frame in frames]
    speed_axis = axes[1, 0]
    forward_axis = axes[1, 1]
    for mode, color in zip(EXPECTED_MODES, ("#1f77b4", "#ff7f0e"), strict=True):
        speed_axis.plot(
            timestamps,
            [
                frame[mode]["plan_geometry"]["first_step_speed_mps"]
                for frame in frames
            ],
            marker="o",
            color=color,
            label=mode,
        )
        forward_axis.plot(
            timestamps,
            [
                frame[mode]["plan_geometry"]["final_forward_m"]
                for frame in frames
            ],
            marker="o",
            color=color,
            label=mode,
        )
    speed_axis.set(
        title="First predicted step speed",
        xlabel="source time, s",
        ylabel="m/s",
    )
    forward_axis.set(
        title="Three-second forward endpoint",
        xlabel="source time, s",
        ylabel="m",
    )
    for axis in (speed_axis, forward_axis):
        axis.grid(alpha=0.3)
        axis.legend()

    figure.suptitle(
        "SparseDrive ego-status sensitivity — equal reset and warm-up",
        fontsize=15,
    )
    path = output / "ego_status_sensitivity.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    analysis = analyze_reports(
        load_json(args.recorded_report.expanduser().resolve()),
        load_json(args.pose_report.expanduser().resolve()),
    )
    visualization = save_visualization(analysis, output)
    analysis["visualization"] = str(visualization)
    report_path = output / "ego_status_sensitivity.json"
    report_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
