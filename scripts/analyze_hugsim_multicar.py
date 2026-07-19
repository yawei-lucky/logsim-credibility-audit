#!/usr/bin/env python3
"""Create inspectable evidence for a paired HUGSIM multi-actor stress test."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np


CAR_SEMANTIC_ID = 13
RGB_CHANGE_THRESHOLD = 10
DEPTH_CHANGE_THRESHOLD_M = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze paired no-actor and multi-actor HUGSIM runs."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--treatment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--frames",
        default="0,6,12,18,24",
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


def normalized_source_assets(source_assets: dict[str, Any]) -> dict[str, Any]:
    """Correct the legacy runner field name without mutating raw run artifacts."""
    normalized = json.loads(json.dumps(source_assets))
    for asset in normalized.get("vehicle_assets", []):
        state = asset.get("initial_state", {})
        if "yaw_deg" in state:
            state["yaw_rad"] = state.pop("yaw_deg")
    return normalized


def first_failed_timestamp(eval_result: dict[str, Any], metric: str) -> float | None:
    for timestamp, values in eval_result.get("details", {}).items():
        if float(values[metric]) < 1.0:
            return float(timestamp)
    return None


def metric_comparison(
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


def paired_differences(
    baseline_infos: list[dict[str, Any]],
    treatment_infos: list[dict[str, Any]],
    baseline_steps: list[dict[str, Any]],
    treatment_steps: list[dict[str, Any]],
) -> dict[str, float]:
    if len(baseline_infos) != len(treatment_infos):
        raise ValueError("Paired runs have different observation counts.")
    if len(baseline_steps) != len(treatment_steps):
        raise ValueError("Paired runs have different completed-step counts.")
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


def front_difference(
    baseline_observation: dict[str, Any],
    treatment_observation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    baseline_rgb = baseline_observation["rgb"]["CAM_FRONT"]
    treatment_rgb = treatment_observation["rgb"]["CAM_FRONT"]
    baseline_semantic = baseline_observation["semantic"]["CAM_FRONT"]
    treatment_semantic = treatment_observation["semantic"]["CAM_FRONT"]
    baseline_depth = baseline_observation["depth"]["CAM_FRONT"]
    treatment_depth = treatment_observation["depth"]["CAM_FRONT"]

    rgb_abs = np.abs(
        baseline_rgb.astype(np.int16) - treatment_rgb.astype(np.int16)
    )
    rgb_changed = rgb_abs.max(axis=2) > RGB_CHANGE_THRESHOLD
    injected_cars = (treatment_semantic == CAR_SEMANTIC_ID) & (
        baseline_semantic != CAR_SEMANTIC_ID
    )
    depth_abs = np.abs(
        baseline_depth.astype(np.float64) - treatment_depth.astype(np.float64)
    )
    depth_changed = depth_abs > DEPTH_CHANGE_THRESHOLD_M
    car_pixels = int(injected_cars.sum())
    stats = {
        "rgb_changed_pixels": int(rgb_changed.sum()),
        "injected_car_semantic_pixels": car_pixels,
        "depth_changed_pixels": int(depth_changed.sum()),
        "car_mask_supported_by_rgb_fraction": (
            float((rgb_changed & injected_cars).sum() / car_pixels)
            if car_pixels
            else None
        ),
        "car_mask_supported_by_depth_fraction": (
            float((depth_changed & injected_cars).sum() / car_pixels)
            if car_pixels
            else None
        ),
    }
    return stats, {
        "rgb_abs": rgb_abs,
        "injected_cars": injected_cars,
        "depth_abs": depth_abs,
    }


def make_contact_sheet(
    output_path: Path,
    frame_indices: list[int],
    baseline_observations: list[dict[str, Any]],
    treatment_observations: list[dict[str, Any]],
    treatment_infos: list[dict[str, Any]],
    treatment_eval: dict[str, Any],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    columns = (
        "No actors (RGB)",
        "Multi-actor cut-in (RGB)",
        "RGB absolute difference ×4",
        "Injected-car semantic mask",
        "Absolute depth difference",
    )
    figure, axes = plt.subplots(
        len(frame_indices),
        len(columns),
        figsize=(18, 3.5 * len(frame_indices)),
        constrained_layout=True,
    )
    if len(frame_indices) == 1:
        axes = axes[np.newaxis, :]

    detail = treatment_eval.get("details", {})
    for row, frame_index in enumerate(frame_indices):
        base = baseline_observations[frame_index]
        treat = treatment_observations[frame_index]
        _, arrays = front_difference(base, treat)
        timestamp = float(treatment_infos[frame_index]["timestamp"])
        metric = detail.get(str(timestamp), {})
        metric_text = (
            f"TTC={metric.get('ttc', 1):.0f}, NC={metric.get('nc', 1):.0f}"
            if frame_index > 0
            else "initial observation"
        )

        axes[row, 0].imshow(base["rgb"]["CAM_FRONT"])
        axes[row, 1].imshow(treat["rgb"]["CAM_FRONT"])
        axes[row, 2].imshow(
            np.clip(arrays["rgb_abs"].astype(np.float32) * 4.0, 0, 255).astype(
                np.uint8
            )
        )
        overlay = treat["rgb"]["CAM_FRONT"].astype(np.float32) * 0.35
        overlay[arrays["injected_cars"]] = np.array([255.0, 45.0, 45.0])
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
        axes[row, 0].set_ylabel(
            f"t={timestamp:.2f}s\n{metric_text}",
            fontsize=11,
        )
        for column in range(len(columns)):
            axes[row, column].set_xticks([])
            axes[row, column].set_yticks([])

    for column, title in enumerate(columns):
        axes[0, column].set_title(title, fontsize=12)
    figure.suptitle(
        "HUGSIM strong intervention: lead vehicle plus right-side cut-in",
        fontsize=16,
    )
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def make_trajectory_risk_plot(
    output_path: Path,
    baseline_eval: dict[str, Any],
    treatment_eval: dict[str, Any],
    treatment_infos: list[dict[str, Any]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ego = np.asarray([info["ego_box"][:2] for info in treatment_infos], dtype=float)
    actor_count = max(len(info["obj_boxes"]) for info in treatment_infos)
    actors = [
        np.asarray(
            [info["obj_boxes"][index][:2] for info in treatment_infos],
            dtype=float,
        )
        for index in range(actor_count)
    ]

    figure, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    axes[0].plot(
        ego[:, 1],
        ego[:, 0],
        "-o",
        markersize=3,
        color="black",
        label="ego",
    )
    colors = ("tab:orange", "tab:blue", "tab:purple", "tab:brown")
    names = ("right-side cut-in", "lead vehicle")
    for index, trajectory in enumerate(actors):
        label = names[index] if index < len(names) else f"actor {index}"
        axes[0].plot(
            trajectory[:, 1],
            trajectory[:, 0],
            "-o",
            markersize=3,
            color=colors[index % len(colors)],
            label=label,
        )
        axes[0].annotate(
            f"{label} start",
            (trajectory[0, 1], trajectory[0, 0]),
            fontsize=8,
        )
        axes[0].annotate(
            f"{label} end",
            (trajectory[-1, 1], trajectory[-1, 0]),
            fontsize=8,
        )
    axes[0].axvline(0.0, color="black", linestyle=":", alpha=0.5)
    axes[0].set_xlabel("lateral position y (m)")
    axes[0].set_ylabel("longitudinal position x (m)")
    axes[0].set_title("Top-down trajectories")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[0].set_aspect("equal", adjustable="box")

    metric_times = np.asarray(
        [float(item) for item in treatment_eval["details"].keys()],
        dtype=float,
    )
    colors_by_metric = {"ttc": "tab:orange", "nc": "tab:red", "pdms": "tab:blue"}
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
            linewidth=2,
            color=colors_by_metric[metric],
            label=f"multi-actor {metric.upper()}",
        )
        axes[1].step(
            metric_times,
            baseline_values,
            where="post",
            linestyle=":",
            alpha=0.5,
            color=colors_by_metric[metric],
            label=f"no-actor {metric.upper()}",
        )
    for metric, height in (("ttc", 0.48), ("nc", 0.08)):
        first_failure = first_failed_timestamp(treatment_eval, metric)
        if first_failure is not None:
            axes[1].axvline(
                first_failure,
                color=colors_by_metric[metric],
                linestyle="--",
                alpha=0.6,
            )
            axes[1].text(
                first_failure + 0.04,
                height,
                f"{metric.upper()} fails {first_failure:.2f}s",
            )
    axes[1].set_ylim(-0.08, 1.08)
    axes[1].set_xlabel("simulation time (s)")
    axes[1].set_ylabel("metric value")
    axes[1].set_title("Planned-path risk response")
    axes[1].grid(alpha=0.25)
    axes[1].legend(ncol=2, fontsize=8)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def add_label(image: np.ndarray, label: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    band_height = 34
    canvas = np.zeros(
        (image.shape[0] + band_height, image.shape[1], 3),
        dtype=np.uint8,
    )
    canvas[band_height:] = image
    pil_image = Image.fromarray(canvas)
    ImageDraw.Draw(pil_image).text((10, 9), label, fill=(255, 255, 255))
    return np.asarray(pil_image)


def make_video(
    output_path: Path,
    baseline_observations: list[dict[str, Any]],
    treatment_observations: list[dict[str, Any]],
) -> None:
    from moviepy import ImageSequenceClip

    frames = []
    for base, treat in zip(
        baseline_observations,
        treatment_observations,
        strict=True,
    ):
        base_rgb = base["rgb"]["CAM_FRONT"]
        treat_rgb = treat["rgb"]["CAM_FRONT"]
        _, arrays = front_difference(base, treat)
        difference = np.clip(
            arrays["rgb_abs"].astype(np.float32) * 4.0,
            0,
            255,
        ).astype(np.uint8)
        frames.append(
            np.concatenate(
                (
                    add_label(base_rgb, "No actors"),
                    add_label(treat_rgb, "Lead + cut-in"),
                    add_label(difference, "RGB difference x4"),
                ),
                axis=1,
            )
        )
    ImageSequenceClip(frames, fps=4).write_videofile(
        str(output_path),
        logger=None,
    )


def main() -> int:
    args = parse_args()
    baseline = args.baseline.expanduser().resolve()
    treatment = args.treatment.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    baseline_observations = load_pickle(baseline / "observations.pkl")
    treatment_observations = load_pickle(treatment / "observations.pkl")
    baseline_infos = load_pickle(baseline / "infos.pkl")
    treatment_infos = load_pickle(treatment / "infos.pkl")
    baseline_steps = load_pickle(baseline / "audit_steps.pkl")
    treatment_steps = load_pickle(treatment / "audit_steps.pkl")
    baseline_eval = load_json(baseline / "eval.json")
    treatment_eval = load_json(treatment / "eval.json")
    treatment_audit = load_json(treatment / "audit_summary.json")

    if len(baseline_observations) != len(treatment_observations):
        raise ValueError("Paired runs have different observation counts.")
    if not treatment_infos or len(treatment_infos[0]["obj_boxes"]) < 2:
        raise ValueError("Treatment does not contain at least two actors.")

    requested_frames = [int(item) for item in args.frames.split(",")]
    frame_indices = sorted(
        {item for item in requested_frames if 0 <= item < len(treatment_observations)}
    )
    if not frame_indices:
        raise ValueError("No requested contact-sheet frame is available.")

    contact_sheet = output / "front_multicar_contact_sheet.png"
    trajectory_plot = output / "multicar_trajectory_and_risk.png"
    front_video = output / "front_multicar_comparison.mp4"
    make_contact_sheet(
        contact_sheet,
        frame_indices,
        baseline_observations,
        treatment_observations,
        treatment_infos,
        treatment_eval,
    )
    make_trajectory_risk_plot(
        trajectory_plot,
        baseline_eval,
        treatment_eval,
        treatment_infos,
    )
    make_video(
        front_video,
        baseline_observations,
        treatment_observations,
    )

    frame_evidence = []
    for index, (base, treat) in enumerate(
        zip(baseline_observations, treatment_observations, strict=True)
    ):
        stats, _ = front_difference(base, treat)
        stats["frame_index"] = index
        stats["timestamp"] = float(treatment_infos[index]["timestamp"])
        frame_evidence.append(stats)

    actor_trajectories = []
    actor_count = len(treatment_infos[0]["obj_boxes"])
    for actor_index in range(actor_count):
        actor_trajectories.append(
            {
                "actor_index": actor_index,
                "boxes": [
                    info["obj_boxes"][actor_index] for info in treatment_infos
                ],
            }
        )

    summary = {
        "experiment": "scene-0383 lead vehicle plus right-side cut-in",
        "baseline_run": str(baseline),
        "treatment_run": str(treatment),
        "hugsim_commit": treatment_audit["hugsim_commit"],
        "source_assets": normalized_source_assets(
            treatment_audit["source_assets"]
        ),
        "control": {
            "requested_steps": treatment_audit["requested_steps"],
            "completed_steps": treatment_audit["completed_steps"],
            "paired_run_differences": paired_differences(
                baseline_infos,
                treatment_infos,
                baseline_steps,
                treatment_steps,
            ),
        },
        "outcome": {
            "actual_collision_observed": any(
                bool(info.get("collision", False)) for info in treatment_infos
            ),
            "first_ttc_failure_s": first_failed_timestamp(treatment_eval, "ttc"),
            "first_nc_failure_s": first_failed_timestamp(treatment_eval, "nc"),
            "metric_comparison": metric_comparison(
                baseline_eval,
                treatment_eval,
            ),
        },
        "actor_trajectories": actor_trajectories,
        "front_frame_evidence": frame_evidence,
        "visual_artifacts": {
            "contact_sheet": str(contact_sheet),
            "trajectory_and_risk": str(trajectory_plot),
            "front_video": str(front_video),
        },
        "interpretation_guardrail": (
            "This stress test evaluates HUGSIM multi-instance rendering, "
            "actor-state evolution, and internal planned-path risk response. "
            "The deterministic writer is not an AD agent."
        ),
    }
    with (output / "multicar_summary.json").open("w", encoding="utf-8") as stream:
        json.dump(jsonable(summary), stream, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
