#!/usr/bin/env python3
"""Audit actor attribution and finite-rollout sensitivity in HUGSIM runs."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from analyze_hugsim_multicar import (
    first_failed_timestamp,
    jsonable,
    load_json,
    load_pickle,
    normalized_source_assets,
    paired_differences,
    validate_run_pairing,
)


METRICS = ("nc", "dac", "ttc", "c", "pdms")
CONDITION_LABELS = {
    "no_actor": "No actors",
    "lead_only": "Lead only",
    "cut_in_only": "Cut-in only",
    "lead_and_cut_in": "Lead + cut-in",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a 2x2 actor-removal experiment and compare a short "
            "multi-actor run with an extended run sharing the same prefix."
        )
    )
    parser.add_argument("--no-actor", required=True, type=Path)
    parser.add_argument("--lead-only", required=True, type=Path)
    parser.add_argument("--cut-in-only", required=True, type=Path)
    parser.add_argument("--lead-and-cut-in", required=True, type=Path)
    parser.add_argument("--short-lead-and-cut-in", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--frames",
        default="0,12,19,20,24,36",
        help="Comma-separated video-frame indices for the contact sheet.",
    )
    return parser.parse_args()


def load_data_frames(path: Path) -> list[dict[str, Any]]:
    payload = load_pickle(path / "data.pkl")
    if len(payload) != 1 or "frames" not in payload[0]:
        raise ValueError(f"Unexpected HUGSIM data structure: {path / 'data.pkl'}")
    return payload[0]["frames"]


def valid_window_summary(
    eval_result: dict[str, Any],
    cutoff_s: float,
) -> dict[str, Any]:
    details = [
        (float(timestamp), values)
        for timestamp, values in eval_result["details"].items()
        if float(timestamp) <= cutoff_s + 1e-9
    ]
    if not details:
        raise ValueError("No metric frames fall inside the horizon-valid window.")
    return {
        "end_s": float(cutoff_s),
        "frame_count": len(details),
        "mean_metrics": {
            metric: float(np.mean([values[metric] for _, values in details]))
            for metric in METRICS
        },
        "first_failure_s": {
            metric: next(
                (
                    timestamp
                    for timestamp, values in details
                    if float(values[metric]) < 1.0
                ),
                None,
            )
            for metric in ("ttc", "nc")
        },
    }


def factorial_effects(
    condition_metrics: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    effects: dict[str, dict[str, float]] = {}
    for metric in METRICS:
        no_actor = condition_metrics["no_actor"][metric]
        lead = condition_metrics["lead_only"][metric]
        cut_in = condition_metrics["cut_in_only"][metric]
        both = condition_metrics["lead_and_cut_in"][metric]
        effects[metric] = {
            "lead_without_cut_in": float(lead - no_actor),
            "cut_in_without_lead": float(cut_in - no_actor),
            "lead_with_cut_in": float(both - cut_in),
            "cut_in_with_lead": float(both - lead),
            "interaction": float(both - lead - cut_in + no_actor),
        }
    return effects


def maximum_prefix_differences(
    short_infos: list[dict[str, Any]],
    extended_infos: list[dict[str, Any]],
    short_steps: list[dict[str, Any]],
    extended_steps: list[dict[str, Any]],
) -> dict[str, float]:
    if len(extended_infos) < len(short_infos):
        raise ValueError("Extended run is shorter than the short-run prefix.")
    if len(extended_steps) < len(short_steps):
        raise ValueError("Extended run has fewer completed steps than the short run.")

    ego = []
    actors = []
    timestamps = []
    for short, extended in zip(
        short_infos,
        extended_infos[: len(short_infos)],
        strict=True,
    ):
        ego.append(
            float(
                np.max(
                    np.abs(
                        np.asarray(short["ego_box"], dtype=np.float64)
                        - np.asarray(extended["ego_box"], dtype=np.float64)
                    )
                )
            )
        )
        actors.append(
            float(
                np.max(
                    np.abs(
                        np.asarray(short["obj_boxes"], dtype=np.float64)
                        - np.asarray(extended["obj_boxes"], dtype=np.float64)
                    )
                )
            )
        )
        timestamps.append(
            abs(float(short["timestamp"]) - float(extended["timestamp"]))
        )

    actions = []
    plans = []
    for short, extended in zip(
        short_steps,
        extended_steps[: len(short_steps)],
        strict=True,
    ):
        actions.append(
            max(
                abs(
                    float(short["action"]["acc"])
                    - float(extended["action"]["acc"])
                ),
                abs(
                    float(short["action"]["steer_rate"])
                    - float(extended["action"]["steer_rate"])
                ),
            )
        )
        plans.append(
            float(
                np.max(
                    np.abs(
                        np.asarray(short["plan_traj"], dtype=np.float64)
                        - np.asarray(extended["plan_traj"], dtype=np.float64)
                    )
                )
            )
        )
    return {
        "maximum_timestamp_absolute_difference": max(timestamps),
        "maximum_ego_box_absolute_difference": max(ego),
        "maximum_actor_box_absolute_difference": max(actors),
        "maximum_action_absolute_difference": max(actions),
        "maximum_plan_absolute_difference": max(plans),
    }


def validate_prefix_provenance(
    short_audit: dict[str, Any],
    extended_audit: dict[str, Any],
) -> dict[str, Any]:
    fields = {
        "hugsim_commit": (
            short_audit.get("hugsim_commit"),
            extended_audit.get("hugsim_commit"),
        ),
        "control_convention": (
            short_audit.get("control_convention"),
            extended_audit.get("control_convention"),
        ),
        "scene_cfg_sha256": (
            short_audit.get("source_assets", {}).get("scene_cfg_sha256"),
            extended_audit.get("source_assets", {}).get("scene_cfg_sha256"),
        ),
        "scenario_yaml_sha256": (
            short_audit.get("source_assets", {}).get("scenario_yaml_sha256"),
            extended_audit.get("source_assets", {}).get("scenario_yaml_sha256"),
        ),
        "vehicle_assets": (
            normalized_source_assets(
                short_audit.get("source_assets", {})
            ).get("vehicle_assets"),
            normalized_source_assets(
                extended_audit.get("source_assets", {})
            ).get("vehicle_assets"),
        ),
    }
    failures = [
        f"{name} differs"
        for name, (short_value, extended_value) in fields.items()
        if short_value != extended_value
    ]
    if short_audit.get("eval_error") is not None:
        failures.append("short-run scoring failed")
    if extended_audit.get("eval_error") is not None:
        failures.append("extended-run scoring failed")
    if failures:
        raise ValueError(
            "Short/extended provenance validation failed: "
            + "; ".join(failures)
        )
    return {
        "status": "passed",
        "matched_fields": list(fields),
    }


def rectangle(box: list[float] | np.ndarray) -> Any:
    from shapely.geometry import Polygon

    x, y, _, width, length, _, yaw = np.asarray(box, dtype=np.float64)
    cosine = np.cos(yaw)
    sine = np.sin(yaw)
    x_offsets = np.asarray([length / 2, length / 2, -length / 2, -length / 2])
    y_offsets = np.asarray([width / 2, -width / 2, -width / 2, width / 2])
    xs = x + x_offsets * cosine - y_offsets * sine
    ys = y + x_offsets * sine + y_offsets * cosine
    return Polygon(np.stack([xs, ys], axis=1))


def actual_actor_clearances(
    infos: list[dict[str, Any]],
) -> dict[str, Any]:
    actor_count = max(len(info["obj_boxes"]) for info in infos)
    distances = [[] for _ in range(actor_count)]
    for info in infos:
        ego_polygon = rectangle(info["ego_box"])
        for actor_index, actor_box in enumerate(info["obj_boxes"]):
            distances[actor_index].append(
                float(ego_polygon.distance(rectangle(actor_box)))
            )
    return {
        "timestamps_s": [float(info["timestamp"]) for info in infos],
        "actors": [
            {
                "actor_index": actor_index,
                "clearance_m": values,
                "minimum_clearance_m": float(min(values)),
                "minimum_clearance_timestamp_s": float(
                    infos[int(np.argmin(values))]["timestamp"]
                ),
            }
            for actor_index, values in enumerate(distances)
        ],
    }


def sampled_future_actor_boxes(
    frames: list[dict[str, Any]],
    frame_index: int,
) -> tuple[list[list[list[float]]], float]:
    frame = frames[frame_index]
    timestep = float(frame["planned_traj"]["timestep"])
    planned_horizon_s = (
        len(frame["planned_traj"]["traj"]) * timestep
    )
    target_timestamp = float(frame["time_stamp"])
    final_timestamp = target_timestamp + planned_horizon_s
    sampled = []
    current_index = frame_index
    while target_timestamp <= final_timestamp + 1e-5:
        if current_index >= len(frames):
            break
        candidate = frames[current_index]
        if abs(target_timestamp - float(candidate["time_stamp"])) < 1e-5:
            sampled.append(candidate["obj_boxes"])
            target_timestamp += timestep
        current_index += 1
    return sampled, planned_horizon_s


def actor_hits_for_frame(
    frames: list[dict[str, Any]],
    frame_index: int,
    shift_s: float = 0.0,
) -> dict[str, Any]:
    frame = frames[frame_index]
    ego_box = frame["ego_box"]
    ego_x, ego_y, _, _, _, _, ego_yaw = ego_box
    planned = np.concatenate(
        (
            np.asarray([[ego_x, ego_y, ego_yaw]], dtype=np.float64),
            np.asarray(frame["planned_traj"]["traj"], dtype=np.float64),
        ),
        axis=0,
    )
    if shift_s:
        timestep = float(frame["planned_traj"]["timestep"])
        velocities = np.diff(planned[:, :2], axis=0) / timestep
        velocities = np.vstack([velocities[0], velocities])
        planned[:, :2] += velocities * shift_s

    actor_history, horizon_s = sampled_future_actor_boxes(frames, frame_index)
    hits = []
    padding_used = False
    for planned_index, planned_box_state in enumerate(planned):
        history_index = planned_index
        if history_index >= len(actor_history):
            history_index = -1
            padding_used = True
        if not actor_history:
            continue
        ego_planned_box = list(ego_box)
        ego_planned_box[0] = float(planned_box_state[0])
        ego_planned_box[1] = float(planned_box_state[1])
        ego_planned_box[6] = float(planned_box_state[2])
        ego_polygon = rectangle(ego_planned_box)
        for actor_index, actor_box in enumerate(actor_history[history_index]):
            if ego_polygon.intersects(rectangle(actor_box)):
                hits.append(
                    {
                        "planned_index": planned_index,
                        "actor_index": actor_index,
                    }
                )
    return {
        "hits": hits,
        "padding_used": padding_used,
        "sampled_actor_states": len(actor_history),
        "required_actor_states": len(planned),
        "planned_horizon_s": horizon_s,
    }


def failed_event_attribution(
    frames: list[dict[str, Any]],
    eval_result: dict[str, Any],
) -> list[dict[str, Any]]:
    frame_by_timestamp = {
        round(float(frame["time_stamp"]), 8): index
        for index, frame in enumerate(frames)
    }
    events = []
    for timestamp_text, values in eval_result["details"].items():
        failed_metrics = [
            metric for metric in ("nc", "ttc") if float(values[metric]) < 1.0
        ]
        if not failed_metrics:
            continue
        timestamp = float(timestamp_text)
        frame_index = frame_by_timestamp[round(timestamp, 8)]
        event: dict[str, Any] = {
            "timestamp_s": timestamp,
            "failed_metrics": failed_metrics,
            "nc": actor_hits_for_frame(frames, frame_index),
            "ttc": {},
        }
        for shift_s in (0.5, 1.0):
            event["ttc"][str(shift_s)] = actor_hits_for_frame(
                frames,
                frame_index,
                shift_s=shift_s,
            )
        events.append(event)
    return events


def extract_front_frames(video_path: Path) -> list[np.ndarray]:
    from moviepy import VideoFileClip

    clip = VideoFileClip(str(video_path))
    try:
        frames = []
        for frame in clip.iter_frames():
            height, width = frame.shape[:2]
            frames.append(
                frame[: height // 2, width // 3 : 2 * width // 3].astype(
                    np.uint8
                )
            )
        return frames
    finally:
        clip.close()


def add_label(image: np.ndarray, label: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    band_height = 34
    canvas = np.zeros(
        (image.shape[0] + band_height, image.shape[1], 3),
        dtype=np.uint8,
    )
    canvas[band_height:] = image
    rendered = Image.fromarray(canvas)
    ImageDraw.Draw(rendered).text((10, 9), label, fill=(255, 255, 255))
    return np.asarray(rendered)


def make_factorial_video(
    output_path: Path,
    condition_frames: dict[str, list[np.ndarray]],
) -> None:
    from moviepy import ImageSequenceClip

    frame_count = min(len(frames) for frames in condition_frames.values())
    rendered = []
    for index in range(frame_count):
        panels = {
            key: add_label(
                condition_frames[key][index],
                CONDITION_LABELS[key],
            )
            for key in CONDITION_LABELS
        }
        top = np.concatenate(
            (panels["no_actor"], panels["lead_only"]),
            axis=1,
        )
        bottom = np.concatenate(
            (panels["cut_in_only"], panels["lead_and_cut_in"]),
            axis=1,
        )
        rendered.append(np.concatenate((top, bottom), axis=0))
    ImageSequenceClip(rendered, fps=4).write_videofile(
        str(output_path),
        logger=None,
    )


def make_contact_sheet(
    output_path: Path,
    condition_frames: dict[str, list[np.ndarray]],
    frame_indices: list[int],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        len(frame_indices),
        len(CONDITION_LABELS),
        figsize=(16, 3.2 * len(frame_indices)),
        constrained_layout=True,
    )
    if len(frame_indices) == 1:
        axes = axes[np.newaxis, :]
    keys = list(CONDITION_LABELS)
    for row, frame_index in enumerate(frame_indices):
        for column, key in enumerate(keys):
            axes[row, column].imshow(condition_frames[key][frame_index])
            axes[row, column].set_xticks([])
            axes[row, column].set_yticks([])
        axes[row, 0].set_ylabel(f"t={frame_index / 4:.2f}s")
    for column, key in enumerate(keys):
        axes[0, column].set_title(CONDITION_LABELS[key])
    figure.suptitle(
        "HUGSIM 2x2 actor-removal experiment (9-second runs)",
        fontsize=16,
    )
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def make_horizon_plot(
    output_path: Path,
    short_eval: dict[str, Any],
    extended_eval: dict[str, Any],
    short_valid_end_s: float,
    extended_valid_end_s: float,
    clearances: dict[str, Any],
    condition_valid_metrics: dict[str, dict[str, float]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 3, figsize=(18, 5.5), constrained_layout=True)

    short_times = np.asarray(
        [float(item) for item in short_eval["details"]],
        dtype=float,
    )
    for metric, color in (("ttc", "tab:orange"), ("nc", "tab:red")):
        short_values = [
            short_eval["details"][str(time)][metric] for time in short_times
        ]
        extended_values = [
            extended_eval["details"][str(time)][metric] for time in short_times
        ]
        axes[0].step(
            short_times,
            short_values,
            where="post",
            color=color,
            linestyle="--",
            label=f"6s {metric.upper()}",
        )
        axes[0].step(
            short_times,
            extended_values,
            where="post",
            color=color,
            linewidth=2,
            label=f"9s-prefix {metric.upper()}",
        )
    axes[0].axvspan(
        short_valid_end_s + 0.25,
        float(short_times[-1]),
        color="gray",
        alpha=0.18,
        label="6s run lacks full future history",
    )
    axes[0].set_title("Same state prefix, different score")
    axes[0].set_xlabel("simulation time (s)")
    axes[0].set_ylabel("binary metric")
    axes[0].set_ylim(-0.08, 1.08)
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)

    timestamps = clearances["timestamps_s"]
    names = ("cut-in actor", "lead actor")
    for actor in clearances["actors"]:
        actor_index = actor["actor_index"]
        axes[1].plot(
            timestamps,
            actor["clearance_m"],
            linewidth=2,
            label=(
                names[actor_index]
                if actor_index < len(names)
                else f"actor {actor_index}"
            ),
        )
        axes[1].scatter(
            [actor["minimum_clearance_timestamp_s"]],
            [actor["minimum_clearance_m"]],
            s=35,
        )
    axes[1].axhline(0.0, color="black", linestyle=":")
    axes[1].set_title("Actual oriented-box clearance")
    axes[1].set_xlabel("simulation time (s)")
    axes[1].set_ylabel("polygon distance (m)")
    axes[1].grid(alpha=0.25)
    axes[1].legend()

    keys = list(CONDITION_LABELS)
    x = np.arange(len(keys))
    width = 0.22
    for offset, metric in enumerate(("nc", "ttc", "pdms")):
        axes[2].bar(
            x + (offset - 1) * width,
            [condition_valid_metrics[key][metric] for key in keys],
            width,
            label=metric.upper(),
        )
    axes[2].set_xticks(x, [CONDITION_LABELS[key] for key in keys], rotation=15)
    axes[2].set_ylim(0, 1.08)
    axes[2].set_title(
        f"Horizon-valid window (0–{extended_valid_end_s:.1f}s)"
    )
    axes[2].set_ylabel("mean metric")
    axes[2].grid(axis="y", alpha=0.25)
    axes[2].legend()

    figure.suptitle(
        "Finite-rollout audit overturns the apparent cut-in risk event",
        fontsize=16,
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    runs = {
        "no_actor": args.no_actor.expanduser().resolve(),
        "lead_only": args.lead_only.expanduser().resolve(),
        "cut_in_only": args.cut_in_only.expanduser().resolve(),
        "lead_and_cut_in": args.lead_and_cut_in.expanduser().resolve(),
    }
    short_run = args.short_lead_and_cut_in.expanduser().resolve()
    output = args.output.expanduser().resolve()

    audits = {
        key: load_json(path / "audit_summary.json")
        for key, path in runs.items()
    }
    infos = {
        key: load_pickle(path / "infos.pkl")
        for key, path in runs.items()
    }
    steps = {
        key: load_pickle(path / "audit_steps.pkl")
        for key, path in runs.items()
    }
    evals = {
        key: load_json(path / "eval.json")
        for key, path in runs.items()
    }

    pairing = {}
    for key in ("lead_only", "cut_in_only", "lead_and_cut_in"):
        pairing[key] = {
            "input_validation": validate_run_pairing(
                audits["no_actor"],
                audits[key],
                infos["no_actor"],
                infos[key],
                steps["no_actor"],
                steps[key],
            ),
            "output_differences": paired_differences(
                infos["no_actor"],
                infos[key],
                steps["no_actor"],
                steps[key],
            ),
        }

    extended_frames = load_data_frames(runs["lead_and_cut_in"])
    short_frames = load_data_frames(short_run)
    planning_horizon_s = (
        len(extended_frames[0]["planned_traj"]["traj"])
        * float(extended_frames[0]["planned_traj"]["timestep"])
    )
    extended_final_timestamp_s = float(extended_frames[-1]["time_stamp"])
    short_final_timestamp_s = float(short_frames[-1]["time_stamp"])
    extended_valid_end_s = extended_final_timestamp_s - planning_horizon_s
    short_valid_end_s = short_final_timestamp_s - planning_horizon_s

    valid_windows = {
        key: valid_window_summary(evals[key], extended_valid_end_s)
        for key in runs
    }
    valid_metrics = {
        key: summary["mean_metrics"]
        for key, summary in valid_windows.items()
    }

    short_infos = load_pickle(short_run / "infos.pkl")
    short_steps = load_pickle(short_run / "audit_steps.pkl")
    short_eval = load_json(short_run / "eval.json")
    short_audit = load_json(short_run / "audit_summary.json")
    prefix_provenance = validate_prefix_provenance(
        short_audit,
        audits["lead_and_cut_in"],
    )
    prefix_differences = maximum_prefix_differences(
        short_infos,
        infos["lead_and_cut_in"],
        short_steps,
        steps["lead_and_cut_in"],
    )
    if any(value != 0.0 for value in prefix_differences.values()):
        raise ValueError(
            "Short and extended runs do not have an exact common prefix."
        )

    actor_state_invariance = {
        "cut_in_only_vs_combined_actor0_max_box_difference": float(
            np.max(
                np.abs(
                    np.asarray(
                        [info["obj_boxes"][0] for info in infos["cut_in_only"]],
                        dtype=np.float64,
                    )
                    - np.asarray(
                        [
                            info["obj_boxes"][0]
                            for info in infos["lead_and_cut_in"]
                        ],
                        dtype=np.float64,
                    )
                )
            )
        ),
        "lead_only_vs_combined_actor1_max_box_difference": float(
            np.max(
                np.abs(
                    np.asarray(
                        [info["obj_boxes"][0] for info in infos["lead_only"]],
                        dtype=np.float64,
                    )
                    - np.asarray(
                        [
                            info["obj_boxes"][1]
                            for info in infos["lead_and_cut_in"]
                        ],
                        dtype=np.float64,
                    )
                )
            )
        ),
    }

    clearances = actual_actor_clearances(infos["lead_and_cut_in"])
    short_events = failed_event_attribution(short_frames, short_eval)

    condition_frames = {
        key: extract_front_frames(path / "video.mp4")
        for key, path in runs.items()
    }
    available_frame_count = min(
        len(frames) for frames in condition_frames.values()
    )
    requested_frames = [int(item) for item in args.frames.split(",")]
    frame_indices = sorted(
        {
            item
            for item in requested_frames
            if 0 <= item < available_frame_count
        }
    )
    if not frame_indices:
        raise ValueError("No requested contact-sheet frame is available.")

    short_exposed_failures = {
        metric: first_failed_timestamp(short_eval, metric)
        for metric in ("ttc", "nc")
    }
    extended_prefix_failures = {
        metric: next(
            (
                float(timestamp)
                for timestamp, values in evals["lead_and_cut_in"][
                    "details"
                ].items()
                if float(timestamp) <= short_final_timestamp_s + 1e-9
                and float(values[metric]) < 1.0
            ),
            None,
        )
        for metric in ("ttc", "nc")
    }
    if not short_events:
        raise ValueError("Short run contains no failed TTC/NC event to audit.")
    if any(
        event["timestamp_s"] <= short_valid_end_s + 1e-9
        for event in short_events
    ):
        raise ValueError(
            "A short-run failure occurs inside its complete-history window."
        )
    for event in short_events:
        relevant_results = []
        if "nc" in event["failed_metrics"]:
            relevant_results.append(event["nc"])
        if "ttc" in event["failed_metrics"]:
            relevant_results.extend(event["ttc"].values())
        hit_results = [
            result for result in relevant_results if result["hits"]
        ]
        if not hit_results:
            raise ValueError(
                "A failed metric could not be attributed to an actor hit."
            )
        for result in hit_results:
            if not result["padding_used"]:
                raise ValueError(
                    "A short-run failed actor hit did not use tail padding."
                )
            if any(
                hit["planned_index"] < result["sampled_actor_states"]
                for hit in result["hits"]
            ):
                raise ValueError(
                    "A short-run failed actor hit used a real future state."
                )
            if any(hit["actor_index"] != 0 for hit in result["hits"]):
                raise ValueError(
                    "A short-run failed actor hit was not cut-in actor0."
                )
    if any(value is not None for value in extended_prefix_failures.values()):
        raise ValueError(
            "The extended run still fails within the short-run prefix."
        )

    output.mkdir(parents=True, exist_ok=False)
    factorial_video = output / "factorial_front_comparison.mp4"
    contact_sheet = output / "factorial_contact_sheet.png"
    horizon_plot = output / "horizon_sensitivity_and_clearance.png"
    make_factorial_video(factorial_video, condition_frames)
    make_contact_sheet(contact_sheet, condition_frames, frame_indices)
    make_horizon_plot(
        horizon_plot,
        short_eval,
        evals["lead_and_cut_in"],
        short_valid_end_s,
        extended_valid_end_s,
        clearances,
        valid_metrics,
    )

    summary = {
        "experiment": "scene-0383 2x2 actor-removal and rollout-horizon audit",
        "runs": {key: str(path) for key, path in runs.items()},
        "short_run": str(short_run),
        "pairing": pairing,
        "actor_state_invariance": actor_state_invariance,
        "finite_rollout_audit": {
            "planned_waypoints": len(
                extended_frames[0]["planned_traj"]["traj"]
            ),
            "planned_timestep_s": float(
                extended_frames[0]["planned_traj"]["timestep"]
            ),
            "required_future_actor_history_s": planning_horizon_s,
            "short_run_final_timestamp_s": short_final_timestamp_s,
            "short_run_horizon_valid_end_s": short_valid_end_s,
            "extended_run_final_timestamp_s": extended_final_timestamp_s,
            "extended_run_horizon_valid_end_s": extended_valid_end_s,
            "short_vs_extended_prefix_differences": prefix_differences,
            "short_vs_extended_provenance": prefix_provenance,
            "short_run_first_failures_s": short_exposed_failures,
            "extended_run_same_prefix_first_failures_s": (
                extended_prefix_failures
            ),
            "short_run_failed_event_actor_attribution": short_events,
        },
        "horizon_valid_windows": valid_windows,
        "factorial_effects_on_horizon_valid_mean_metrics": factorial_effects(
            valid_metrics
        ),
        "actual_oriented_box_clearance": clearances,
        "decisions": {
            "strict_pairing_and_actor_removal_execution": "accepted",
            "multi_actor_rendering_and_state_evolution": "accepted",
            "old_6s_nc_ttc_as_dynamic_risk_evidence": "rejected",
            "actual_collision_or_near_miss": "rejected",
            "scripted_merge_realism": "down-weighted",
            "sensor_evidence_for_e2e_evaluation": "down-weighted",
            "ad_agent_response": "rejected",
            "global_hugsim_credibility": "rejected",
        },
        "interpretation": (
            "The old 6-second and new 9-second combined runs have an exact "
            "state/action/plan prefix, yet the old tail TTC/NC failures "
            "disappear when future actor history is available. The apparent "
            "risk event is therefore a finite-rollout scoring artifact, not "
            "credible dynamic-risk evidence."
        ),
        "visual_artifacts": {
            "factorial_video": str(factorial_video),
            "contact_sheet": str(contact_sheet),
            "horizon_sensitivity_and_clearance": str(horizon_plot),
        },
    }
    with (output / "horizon_factorial_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(jsonable(summary), stream, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
