#!/usr/bin/env python3
"""Analyze a synchronized no-actor / actor HUGSIM counterfactual pair."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np


CAMERA_ORDER = (
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
)
CAR_SEMANTIC_ID = 13
RGB_CHANGE_THRESHOLD = 10
DEPTH_CHANGE_THRESHOLD_M = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare synchronized HUGSIM baseline and actor-injected runs."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--treatment", required=True, type=Path)
    parser.add_argument(
        "--adjacent-control",
        type=Path,
        help=(
            "Optional third run with the same actor moved outside the ego path. "
            "Used to distinguish relation sensitivity from actor-presence sensitivity."
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--frames",
        default="0,6,12,16,20",
        help="Comma-separated observation indices for the contact sheet.",
    )
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def safe_fraction(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def first_failed_timestamp(eval_result: dict[str, Any], metric: str) -> float | None:
    for timestamp, values in eval_result.get("details", {}).items():
        if float(values[metric]) < 1.0:
            return float(timestamp)
    return None


def metric_delta(
    baseline_eval: dict[str, Any],
    treatment_eval: dict[str, Any],
) -> dict[str, dict[str, float]]:
    keys = ("nc", "dac", "ttc", "c", "pdms", "rc", "hdscore")
    return {
        key: {
            "baseline": float(baseline_eval[key]),
            "treatment": float(treatment_eval[key]),
            "delta": float(treatment_eval[key] - baseline_eval[key]),
        }
        for key in keys
    }


def camera_frame_evidence(
    baseline_observation: dict[str, Any],
    treatment_observation: dict[str, Any],
    camera: str,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    baseline_rgb = baseline_observation["rgb"][camera]
    treatment_rgb = treatment_observation["rgb"][camera]
    baseline_semantic = baseline_observation["semantic"][camera]
    treatment_semantic = treatment_observation["semantic"][camera]
    baseline_depth = baseline_observation["depth"][camera]
    treatment_depth = treatment_observation["depth"][camera]

    rgb_abs = np.abs(
        baseline_rgb.astype(np.int16) - treatment_rgb.astype(np.int16)
    )
    rgb_changed = rgb_abs.max(axis=2) > RGB_CHANGE_THRESHOLD
    semantic_changed = baseline_semantic != treatment_semantic
    injected_car = (treatment_semantic == CAR_SEMANTIC_ID) & (
        baseline_semantic != CAR_SEMANTIC_ID
    )
    depth_abs = np.abs(
        baseline_depth.astype(np.float64) - treatment_depth.astype(np.float64)
    )
    depth_changed = depth_abs > DEPTH_CHANGE_THRESHOLD_M

    injected_pixels = int(injected_car.sum())
    rgb_overlap = int((rgb_changed & injected_car).sum())
    depth_overlap = int((depth_changed & injected_car).sum())
    stats = {
        "rgb_mean_absolute_difference": float(rgb_abs.mean()),
        "rgb_changed_pixels": int(rgb_changed.sum()),
        "semantic_changed_pixels": int(semantic_changed.sum()),
        "injected_car_semantic_pixels": injected_pixels,
        "depth_changed_pixels": int(depth_changed.sum()),
        "max_depth_difference_m": float(depth_abs.max()),
        "actor_mask_supported_by_rgb_fraction": safe_fraction(
            rgb_overlap, injected_pixels
        ),
        "actor_mask_supported_by_depth_fraction": safe_fraction(
            depth_overlap, injected_pixels
        ),
    }
    arrays = {
        "rgb_abs": rgb_abs,
        "rgb_changed": rgb_changed,
        "semantic_changed": semantic_changed,
        "injected_car": injected_car,
        "depth_abs": depth_abs,
        "depth_changed": depth_changed,
    }
    return stats, arrays


def actor_geometry(infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline = []
    for info in infos:
        ego = np.asarray(info["ego_box"], dtype=np.float64)
        actors = info["obj_boxes"]
        row: dict[str, Any] = {
            "timestamp": float(info["timestamp"]),
            "ego_center_xy": ego[:2],
            "ego_yaw": float(ego[6]),
            "actual_collision": bool(info.get("collision", False)),
            "actor_count": len(actors),
        }
        if actors:
            actor = np.asarray(actors[0], dtype=np.float64)
            center_distance = float(np.linalg.norm(actor[:2] - ego[:2]))
            row.update(
                {
                    "actor_center_xy": actor[:2],
                    "actor_yaw": float(actor[6]),
                    "center_distance_m": center_distance,
                    # Valid for this controlled pair: both boxes are aligned
                    # with the longitudinal x axis and have equal lateral y.
                    "longitudinal_box_clearance_m": float(
                        actor[0] - ego[0] - 0.5 * (actor[4] + ego[4])
                    ),
                }
            )
        timeline.append(row)
    return timeline


def aligned_run_differences(
    baseline_infos: list[dict[str, Any]],
    treatment_infos: list[dict[str, Any]],
    baseline_steps: list[dict[str, Any]],
    treatment_steps: list[dict[str, Any]],
) -> dict[str, float]:
    ego_differences = [
        np.max(
            np.abs(
                np.asarray(base["ego_box"], dtype=np.float64)
                - np.asarray(treat["ego_box"], dtype=np.float64)
            )
        )
        for base, treat in zip(baseline_infos, treatment_infos, strict=True)
    ]
    action_differences = [
        max(
            abs(float(base["action"]["acc"]) - float(treat["action"]["acc"])),
            abs(
                float(base["action"]["steer_rate"])
                - float(treat["action"]["steer_rate"])
            ),
        )
        for base, treat in zip(baseline_steps, treatment_steps, strict=True)
    ]
    return {
        "maximum_ego_box_absolute_difference": float(max(ego_differences)),
        "maximum_action_absolute_difference": float(max(action_differences)),
    }


def make_contact_sheet(
    output_path: Path,
    frame_indices: list[int],
    timestamps: list[float],
    baseline_observations: list[dict[str, Any]],
    treatment_observations: list[dict[str, Any]],
    treatment_eval: dict[str, Any],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    columns = (
        "No actor (RGB)",
        "Actor injected (RGB)",
        "RGB absolute difference ×5",
        "Injected car semantic mask",
        "Absolute depth difference",
    )
    figure, axes = plt.subplots(
        len(frame_indices),
        len(columns),
        figsize=(18, 3.55 * len(frame_indices)),
        constrained_layout=True,
    )
    if len(frame_indices) == 1:
        axes = axes[np.newaxis, :]

    detail = treatment_eval.get("details", {})
    for row, frame_index in enumerate(frame_indices):
        base = baseline_observations[frame_index]
        treat = treatment_observations[frame_index]
        _, arrays = camera_frame_evidence(base, treat, "CAM_FRONT")
        timestamp = timestamps[frame_index]
        metric = detail.get(str(timestamp), {})
        risk = (
            f"TTC={metric.get('ttc', 1):.0f}, NC={metric.get('nc', 1):.0f}"
            if frame_index > 0
            else "initial observation"
        )

        axes[row, 0].imshow(base["rgb"]["CAM_FRONT"])
        axes[row, 1].imshow(treat["rgb"]["CAM_FRONT"])
        axes[row, 2].imshow(
            np.clip(arrays["rgb_abs"].astype(np.float32) * 5.0, 0, 255).astype(
                np.uint8
            )
        )

        overlay = treat["rgb"]["CAM_FRONT"].astype(np.float32) * 0.35
        overlay[arrays["injected_car"]] = np.array([255.0, 45.0, 45.0])
        axes[row, 3].imshow(overlay.astype(np.uint8))

        depth_image = axes[row, 4].imshow(
            arrays["depth_abs"],
            cmap="magma",
            vmin=0,
            vmax=max(1.0, float(np.percentile(arrays["depth_abs"], 99.5))),
        )
        figure.colorbar(
            depth_image,
            ax=axes[row, 4],
            fraction=0.046,
            pad=0.02,
            label="m",
        )

        axes[row, 0].set_ylabel(f"t={timestamp:.2f}s\n{risk}", fontsize=11)
        for column in range(len(columns)):
            axes[row, column].set_xticks([])
            axes[row, column].set_yticks([])

    for column, title in enumerate(columns):
        axes[0, column].set_title(title, fontsize=12)
    figure.suptitle(
        "HUGSIM synchronized counterfactual: only the stationary car changes",
        fontsize=16,
    )
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def make_risk_timeline(
    output_path: Path,
    geometry: list[dict[str, Any]],
    baseline_eval: dict[str, Any],
    treatment_eval: dict[str, Any],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    timestamps = np.array([row["timestamp"] for row in geometry], dtype=float)
    ego_x = np.array([row["ego_center_xy"][0] for row in geometry], dtype=float)
    actor_x = np.array([row["actor_center_xy"][0] for row in geometry], dtype=float)
    clearance = np.array(
        [row["longitudinal_box_clearance_m"] for row in geometry], dtype=float
    )

    metric_times = np.array(
        [float(item) for item in treatment_eval["details"].keys()], dtype=float
    )
    figure, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)

    axes[0].plot(timestamps, ego_x, marker="o", label="ego center x")
    axes[0].plot(timestamps, actor_x, linewidth=2, label="actor center x")
    clearance_axis = axes[0].twinx()
    clearance_axis.plot(
        timestamps,
        clearance,
        color="tab:green",
        marker=".",
        label="box clearance",
    )
    axes[0].set_ylabel("longitudinal position (m)")
    clearance_axis.set_ylabel("actual box clearance (m)", color="tab:green")
    axes[0].grid(alpha=0.25)
    lines, labels = axes[0].get_legend_handles_labels()
    lines2, labels2 = clearance_axis.get_legend_handles_labels()
    axes[0].legend(lines + lines2, labels + labels2, loc="center left")

    colors = {"ttc": "tab:orange", "nc": "tab:red", "pdms": "tab:blue"}
    for metric in ("ttc", "nc", "pdms"):
        treatment_values = [
            treatment_eval["details"][str(time)][metric] for time in metric_times
        ]
        baseline_values = [
            baseline_eval["details"][str(time)][metric] for time in metric_times
        ]
        axes[1].step(
            metric_times,
            treatment_values,
            where="post",
            color=colors[metric],
            linewidth=2,
            label=f"actor {metric.upper()}",
        )
        axes[1].step(
            metric_times,
            baseline_values,
            where="post",
            color=colors[metric],
            linestyle=":",
            alpha=0.45,
            label=f"no-actor {metric.upper()}",
        )

    first_ttc = first_failed_timestamp(treatment_eval, "ttc")
    first_nc = first_failed_timestamp(treatment_eval, "nc")
    if first_ttc is not None:
        axes[1].axvline(first_ttc, color="tab:orange", linestyle="--", alpha=0.6)
        axes[1].text(first_ttc + 0.04, 0.48, f"TTC fails {first_ttc:.2f}s")
    if first_nc is not None:
        axes[1].axvline(first_nc, color="tab:red", linestyle="--", alpha=0.6)
        axes[1].text(first_nc + 0.04, 0.08, f"NC fails {first_nc:.2f}s")
    axes[1].set_ylim(-0.08, 1.08)
    axes[1].set_xlabel("simulation time (s)")
    axes[1].set_ylabel("metric value")
    axes[1].grid(alpha=0.25)
    axes[1].legend(ncol=3, loc="upper center")
    axes[0].set_title(
        "Actual ego motion remains collision-free; planned-path risk metrics diverge"
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def make_relation_control(
    output_path: Path,
    baseline_observation: dict[str, Any],
    treatment_observation: dict[str, Any],
    adjacent_observation: dict[str, Any],
    baseline_eval: dict[str, Any],
    treatment_eval: dict[str, Any],
    adjacent_eval: dict[str, Any],
    timestamp: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(15, 8), constrained_layout=True)
    grid = figure.add_gridspec(2, 3, height_ratios=(2.2, 1.2))
    observations = (
        ("No actor", baseline_observation),
        ("Same-lane actor", treatment_observation),
        ("Adjacent-lane actor", adjacent_observation),
    )
    for column, (title, observation) in enumerate(observations):
        axis = figure.add_subplot(grid[0, column])
        axis.imshow(observation["rgb"]["CAM_FRONT"])
        axis.set_title(title, fontsize=14)
        axis.set_xticks([])
        axis.set_yticks([])

    axis = figure.add_subplot(grid[1, :])
    labels = ("NC", "TTC", "PDMS", "HDScore")
    keys = ("nc", "ttc", "pdms", "hdscore")
    x = np.arange(len(labels))
    width = 0.24
    for offset, (name, result, color) in enumerate(
        (
            ("No actor", baseline_eval, "tab:blue"),
            ("Same lane", treatment_eval, "tab:red"),
            ("Adjacent lane", adjacent_eval, "tab:green"),
        )
    ):
        values = [float(result[key]) for key in keys]
        bars = axis.bar(
            x + (offset - 1) * width,
            values,
            width,
            label=name,
            color=color,
        )
        axis.bar_label(bars, fmt="%.3f", padding=2, fontsize=9)
    axis.set_xticks(x, labels)
    axis.set_ylim(0, 1.12)
    axis.set_ylabel("run-level score")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=3, loc="upper right")
    axis.set_title(
        "Only the same-lane relation changes planned-path risk scores",
        fontsize=14,
    )
    figure.suptitle(
        f"HUGSIM relation negative control at t={timestamp:.2f}s",
        fontsize=17,
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def label_panel(image: np.ndarray, label: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    canvas = Image.new("RGB", (image.shape[1], image.shape[0] + 42), "black")
    canvas.paste(Image.fromarray(image), (0, 42))
    ImageDraw.Draw(canvas).text((12, 12), label, fill="white")
    return np.asarray(canvas)


def make_video(
    output_path: Path,
    timestamps: list[float],
    baseline_observations: list[dict[str, Any]],
    treatment_observations: list[dict[str, Any]],
) -> None:
    from moviepy import ImageSequenceClip

    frames = []
    for timestamp, baseline, treatment in zip(
        timestamps,
        baseline_observations,
        treatment_observations,
        strict=True,
    ):
        baseline_rgb = baseline["rgb"]["CAM_FRONT"]
        treatment_rgb = treatment["rgb"]["CAM_FRONT"]
        _, arrays = camera_frame_evidence(baseline, treatment, "CAM_FRONT")
        difference = np.zeros_like(baseline_rgb)
        difference[arrays["rgb_changed"]] = np.array([255, 230, 40], dtype=np.uint8)
        actor_pixels = arrays["injected_car"]
        difference[actor_pixels] = np.array([255, 45, 45], dtype=np.uint8)
        frames.append(
            np.concatenate(
                [
                    label_panel(baseline_rgb, f"No actor  t={timestamp:.2f}s"),
                    label_panel(treatment_rgb, "Stationary actor"),
                    label_panel(difference, "Changed pixels (red = car semantic)"),
                ],
                axis=1,
            )
        )
    ImageSequenceClip(frames, fps=4).write_videofile(
        str(output_path),
        codec="libx264",
        audio=False,
        logger=None,
    )


def main() -> int:
    args = parse_args()
    baseline = args.baseline.expanduser().resolve()
    treatment = args.treatment.expanduser().resolve()
    adjacent = (
        args.adjacent_control.expanduser().resolve()
        if args.adjacent_control is not None
        else None
    )
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    baseline_observations = load_pickle(baseline / "observations.pkl")
    treatment_observations = load_pickle(treatment / "observations.pkl")
    baseline_infos = load_pickle(baseline / "infos.pkl")
    treatment_infos = load_pickle(treatment / "infos.pkl")
    baseline_steps = load_pickle(baseline / "audit_steps.pkl")
    treatment_steps = load_pickle(treatment / "audit_steps.pkl")
    baseline_summary = load_json(baseline / "audit_summary.json")
    treatment_summary = load_json(treatment / "audit_summary.json")
    baseline_eval = load_json(baseline / "eval.json")
    treatment_eval = load_json(treatment / "eval.json")
    adjacent_observations = None
    adjacent_infos = None
    adjacent_steps = None
    adjacent_summary = None
    adjacent_eval = None
    if adjacent is not None:
        adjacent_observations = load_pickle(adjacent / "observations.pkl")
        adjacent_infos = load_pickle(adjacent / "infos.pkl")
        adjacent_steps = load_pickle(adjacent / "audit_steps.pkl")
        adjacent_summary = load_json(adjacent / "audit_summary.json")
        adjacent_eval = load_json(adjacent / "eval.json")

    lengths = {
        len(baseline_observations),
        len(treatment_observations),
        len(baseline_infos),
        len(treatment_infos),
    }
    if len(lengths) != 1:
        raise ValueError(f"Observation/info lengths are not aligned: {sorted(lengths)}")
    if len(baseline_steps) != len(treatment_steps):
        raise ValueError("Step counts are not aligned")
    if adjacent is not None:
        if len(adjacent_observations) != len(baseline_observations):
            raise ValueError("Adjacent-control observation count is not aligned")
        if len(adjacent_infos) != len(baseline_infos):
            raise ValueError("Adjacent-control info count is not aligned")
        if len(adjacent_steps) != len(baseline_steps):
            raise ValueError("Adjacent-control step count is not aligned")

    timestamps = [float(info["timestamp"]) for info in treatment_infos]
    if timestamps != [float(info["timestamp"]) for info in baseline_infos]:
        raise ValueError("Observation timestamps are not aligned")
    if adjacent is not None and timestamps != [
        float(info["timestamp"]) for info in adjacent_infos
    ]:
        raise ValueError("Adjacent-control timestamps are not aligned")

    frame_indices = [int(item) for item in args.frames.split(",")]
    if any(index < 0 or index >= len(timestamps) for index in frame_indices):
        raise ValueError(f"Frame selection is outside 0..{len(timestamps) - 1}")

    frames: list[dict[str, Any]] = []
    for frame_index, (base, treat) in enumerate(
        zip(baseline_observations, treatment_observations, strict=True)
    ):
        camera_evidence = {}
        for camera in CAMERA_ORDER:
            stats, _ = camera_frame_evidence(base, treat, camera)
            camera_evidence[camera] = stats
        frames.append(
            {
                "frame_index": frame_index,
                "timestamp": timestamps[frame_index],
                "cameras": camera_evidence,
            }
        )

    geometry = actor_geometry(treatment_infos)
    front_actor_frames = [
        frame
        for frame in frames
        if frame["cameras"]["CAM_FRONT"]["injected_car_semantic_pixels"] > 0
    ]
    all_other_camera_changed_pixels = sum(
        frame["cameras"][camera]["rgb_changed_pixels"]
        for frame in frames
        for camera in CAMERA_ORDER
        if camera != "CAM_FRONT"
    )
    actual_collision_frames = [
        row["timestamp"] for row in geometry if row["actual_collision"]
    ]

    summary = {
        "experiment": "scene-0383 synchronized stationary-actor counterfactual",
        "baseline_run": str(baseline),
        "treatment_run": str(treatment),
        "hugsim_commit": treatment_summary["hugsim_commit"],
        "scenario_assets": {
            "baseline": baseline_summary["source_assets"],
            "treatment": treatment_summary["source_assets"],
            "vehicle_model_id": "2024_07_05_15_57_10",
            "vehicle_asset_path": (
                "/home/yawei/HUGSIM_assets/3DRealCar/2024_07_05_15_57_10"
            ),
            "vehicle_gs_sha256": (
                "3d8b314a9c2ae521464f3973edb4122958f8b580e4168bd6047fc0186094d006"
            ),
            "vehicle_wlh_sha256": (
                "edc468f1d24229a56ccfeaf89324e8b6bf46237d90df21980933562d07a8538f"
            ),
        },
        "control": {
            "convention": treatment_summary.get("control_convention"),
            "requested_steps": treatment_summary["requested_steps"],
            "completed_steps": treatment_summary["completed_steps"],
            "paired_run_differences": aligned_run_differences(
                baseline_infos,
                treatment_infos,
                baseline_steps,
                treatment_steps,
            ),
        },
        "outcome": {
            "actual_collision_observed": bool(actual_collision_frames),
            "actual_collision_timestamps": actual_collision_frames,
            "first_treatment_ttc_failure_s": first_failed_timestamp(
                treatment_eval, "ttc"
            ),
            "first_treatment_nc_failure_s": first_failed_timestamp(
                treatment_eval, "nc"
            ),
            "final_actual_longitudinal_box_clearance_m": geometry[-1][
                "longitudinal_box_clearance_m"
            ],
            "metric_comparison": metric_delta(baseline_eval, treatment_eval),
        },
        "cross_modal_evidence": {
            "front_actor_visible_from_s": (
                front_actor_frames[0]["timestamp"] if front_actor_frames else None
            ),
            "front_actor_visible_through_s": (
                front_actor_frames[-1]["timestamp"] if front_actor_frames else None
            ),
            "front_actor_semantic_pixels_initial": (
                front_actor_frames[0]["cameras"]["CAM_FRONT"][
                    "injected_car_semantic_pixels"
                ]
                if front_actor_frames
                else 0
            ),
            "front_actor_semantic_pixels_final": (
                front_actor_frames[-1]["cameras"]["CAM_FRONT"][
                    "injected_car_semantic_pixels"
                ]
                if front_actor_frames
                else 0
            ),
            "front_final_actor_mask_supported_by_rgb_fraction": frames[-1]["cameras"][
                "CAM_FRONT"
            ]["actor_mask_supported_by_rgb_fraction"],
            "front_final_actor_mask_supported_by_depth_fraction": frames[-1][
                "cameras"
            ]["CAM_FRONT"]["actor_mask_supported_by_depth_fraction"],
            "non_front_rgb_changed_pixels_across_all_frames": (
                all_other_camera_changed_pixels
            ),
        },
        "interpretation": {
            "supported": (
                "With identical ego state and control, injecting the stationary "
                "car changes front-camera RGB, semantic, and depth evidence and "
                "causes HUGSIM planned-path TTC/NC metrics to fail. The optional "
                "adjacent-lane negative control tests whether this response is "
                "specific to the same-lane relation."
            ),
            "not_supported": (
                "The run does not show an actual physical collision, an AD-agent "
                "response, or global simulator credibility."
            ),
        },
        "geometry_timeline": geometry,
        "frame_evidence": frames,
        "visual_artifacts": {
            "contact_sheet": str(output / "front_counterfactual_contact_sheet.png"),
            "risk_timeline": str(output / "risk_timeline.png"),
            "front_video": str(output / "front_counterfactual.mp4"),
        },
    }
    if adjacent is not None:
        adjacent_geometry = actor_geometry(adjacent_infos)
        adjacent_actual_collisions = [
            row["timestamp"] for row in adjacent_geometry if row["actual_collision"]
        ]
        summary["negative_control"] = {
            "run": str(adjacent),
            "source_assets": adjacent_summary["source_assets"],
            "actor_initial_center_xy": adjacent_geometry[0]["actor_center_xy"],
            "actual_collision_observed": bool(adjacent_actual_collisions),
            "first_ttc_failure_s": first_failed_timestamp(adjacent_eval, "ttc"),
            "first_nc_failure_s": first_failed_timestamp(adjacent_eval, "nc"),
            "paired_run_differences_from_baseline": aligned_run_differences(
                baseline_infos,
                adjacent_infos,
                baseline_steps,
                adjacent_steps,
            ),
            "metric_comparison_to_baseline": metric_delta(
                baseline_eval,
                adjacent_eval,
            ),
            "result": (
                "The same actor at the same longitudinal distance but 3.5 m "
                "lateral offset leaves NC, TTC, and PDMS at 1.0."
            ),
        }
        summary["visual_artifacts"]["relation_negative_control"] = str(
            output / "relation_negative_control.png"
        )

    with (output / "contrast_summary.json").open("w", encoding="utf-8") as stream:
        json.dump(jsonable(summary), stream, indent=2)
    make_contact_sheet(
        output / "front_counterfactual_contact_sheet.png",
        frame_indices,
        timestamps,
        baseline_observations,
        treatment_observations,
        treatment_eval,
    )
    make_risk_timeline(output / "risk_timeline.png", geometry, baseline_eval, treatment_eval)
    if adjacent is not None:
        make_relation_control(
            output / "relation_negative_control.png",
            baseline_observations[-1],
            treatment_observations[-1],
            adjacent_observations[-1],
            baseline_eval,
            treatment_eval,
            adjacent_eval,
            timestamps[-1],
        )
    make_video(
        output / "front_counterfactual.mp4",
        timestamps,
        baseline_observations,
        treatment_observations,
    )
    print(json.dumps(jsonable(summary["outcome"]), indent=2))
    print(json.dumps(jsonable(summary["cross_modal_evidence"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
