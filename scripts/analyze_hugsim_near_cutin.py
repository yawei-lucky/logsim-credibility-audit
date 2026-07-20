#!/usr/bin/env python3
"""Analyze a horizon-valid HUGSIM near-distance cut-in stress test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from analyze_hugsim_horizon_factorial import (
    actual_actor_clearances,
    failed_event_attribution,
    load_data_frames,
    valid_window_summary,
)
from analyze_hugsim_multicar import (
    jsonable,
    load_json,
    load_pickle,
    paired_differences,
    validate_run_pairing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a 9-second near-distance HUGSIM cut-in run."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--far-cut-in-control", required=True, type=Path)
    parser.add_argument("--near-cut-in", required=True, type=Path)
    parser.add_argument("--cross-modal-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def interpolated_zero_crossing(
    timestamps: list[float],
    values: list[float],
) -> float | None:
    for index in range(len(values) - 1):
        before = float(values[index])
        after = float(values[index + 1])
        if before < 0.0 <= after:
            ratio = -before / (after - before)
            return float(
                timestamps[index]
                + ratio * (timestamps[index + 1] - timestamps[index])
            )
    return None


def make_near_cutin_plot(
    output_path: Path,
    baseline_eval: dict[str, Any],
    far_eval: dict[str, Any],
    near_eval: dict[str, Any],
    near_infos: list[dict[str, Any]],
    valid_end_s: float,
    invalid_start_s: float,
    clearances: dict[str, Any],
    crossing_s: float | None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 3, figsize=(18, 5.8), constrained_layout=True)

    ego = np.asarray([info["ego_box"][:2] for info in near_infos], dtype=float)
    actor0 = np.asarray(
        [info["obj_boxes"][0][:2] for info in near_infos],
        dtype=float,
    )
    actor1 = np.asarray(
        [info["obj_boxes"][1][:2] for info in near_infos],
        dtype=float,
    )
    axes[0].plot(ego[:, 1], ego[:, 0], color="black", linewidth=2, label="ego")
    axes[0].plot(
        actor0[:, 1],
        actor0[:, 0],
        color="tab:orange",
        linewidth=2,
        label="near cut-in",
    )
    axes[0].plot(
        actor1[:, 1],
        actor1[:, 0],
        color="tab:blue",
        linewidth=2,
        label="far lead",
    )
    axes[0].axvline(0.0, color="black", linestyle=":", alpha=0.5)
    axes[0].set_xlabel("lateral position y (m)")
    axes[0].set_ylabel("longitudinal position x (m)")
    axes[0].set_title(
        "Top-down paths"
        + (f"\ncenterline crossing ≈ {crossing_s:.2f}s" if crossing_s else "")
    )
    axes[0].grid(alpha=0.25)
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].legend()

    timestamps = np.asarray(
        [float(item) for item in near_eval["details"]],
        dtype=float,
    )
    conditions = (
        ("no actors TTC", baseline_eval, "gray", ":"),
        ("far cut-in TTC", far_eval, "tab:blue", "--"),
        ("near cut-in TTC", near_eval, "tab:orange", "-"),
    )
    for label, result, color, linestyle in conditions:
        axes[1].step(
            timestamps,
            [result["details"][str(time)]["ttc"] for time in timestamps],
            where="post",
            color=color,
            linestyle=linestyle,
            linewidth=2,
            label=label,
        )
    axes[1].step(
        timestamps,
        [near_eval["details"][str(time)]["nc"] for time in timestamps],
        where="post",
        color="tab:red",
        linewidth=2,
        label="near cut-in NC",
    )
    axes[1].axvspan(
        invalid_start_s,
        float(timestamps[-1]),
        color="gray",
        alpha=0.18,
        label="incomplete future-history tail",
    )
    axes[1].set_ylim(-0.08, 1.08)
    axes[1].set_xlabel("simulation time (s)")
    axes[1].set_ylabel("binary metric")
    axes[1].set_title(f"Metric timeline; valid through {valid_end_s:.1f}s")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)

    names = ("near cut-in", "far lead")
    for actor in clearances["actors"]:
        index = actor["actor_index"]
        axes[2].plot(
            clearances["timestamps_s"],
            actor["clearance_m"],
            linewidth=2,
            label=names[index] if index < len(names) else f"actor {index}",
        )
        axes[2].scatter(
            [actor["minimum_clearance_timestamp_s"]],
            [actor["minimum_clearance_m"]],
            s=40,
        )
    axes[2].axhline(0.0, color="black", linestyle=":")
    axes[2].axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    axes[2].axvspan(
        invalid_start_s,
        float(timestamps[-1]),
        color="gray",
        alpha=0.18,
    )
    axes[2].set_xlabel("simulation time (s)")
    axes[2].set_ylabel("2D oriented-footprint clearance (m)")
    axes[2].set_title("Positive-clearance close pass")
    axes[2].grid(alpha=0.25)
    axes[2].legend()

    figure.suptitle(
        "HUGSIM near cut-in: TTC response without actual collision",
        fontsize=16,
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    baseline = args.baseline.expanduser().resolve()
    far_control = args.far_cut_in_control.expanduser().resolve()
    near = args.near_cut_in.expanduser().resolve()
    cross_modal_report = args.cross_modal_report.expanduser().resolve()
    output = args.output.expanduser().resolve()

    paths = {
        "baseline": baseline,
        "far_cut_in_control": far_control,
        "near_cut_in": near,
    }
    audits = {
        key: load_json(path / "audit_summary.json")
        for key, path in paths.items()
    }
    infos = {
        key: load_pickle(path / "infos.pkl")
        for key, path in paths.items()
    }
    steps = {
        key: load_pickle(path / "audit_steps.pkl")
        for key, path in paths.items()
    }
    evals = {
        key: load_json(path / "eval.json")
        for key, path in paths.items()
    }

    pairing = {}
    for key in ("far_cut_in_control", "near_cut_in"):
        pairing[key] = {
            "input_validation": validate_run_pairing(
                audits["baseline"],
                audits[key],
                infos["baseline"],
                infos[key],
                steps["baseline"],
                steps[key],
            ),
            "output_differences": paired_differences(
                infos["baseline"],
                infos[key],
                steps["baseline"],
                steps[key],
            ),
        }

    frames = load_data_frames(near)
    planned_horizon_s = (
        len(frames[0]["planned_traj"]["traj"])
        * float(frames[0]["planned_traj"]["timestep"])
    )
    final_timestamp_s = float(frames[-1]["time_stamp"])
    valid_end_s = final_timestamp_s - planned_horizon_s
    metric_timestamps = sorted(
        float(timestamp) for timestamp in evals["near_cut_in"]["details"]
    )
    invalid_start_s = next(
        timestamp
        for timestamp in metric_timestamps
        if timestamp > valid_end_s + 1e-9
    )
    valid_windows = {
        key: valid_window_summary(evals[key], valid_end_s)
        for key in paths
    }

    clearances = actual_actor_clearances(infos["near_cut_in"])
    timestamps = [
        float(info["timestamp"]) for info in infos["near_cut_in"]
    ]
    cut_in_lateral = [
        float(info["obj_boxes"][0][1]) for info in infos["near_cut_in"]
    ]
    crossing_s = interpolated_zero_crossing(timestamps, cut_in_lateral)

    all_failed_events = failed_event_attribution(
        frames,
        evals["near_cut_in"],
    )
    valid_failed_events = [
        event
        for event in all_failed_events
        if event["timestamp_s"] <= valid_end_s + 1e-9
    ]
    padded_valid_events = []
    valid_hit_actor_ids = set()
    for event in valid_failed_events:
        for result in event["ttc"].values():
            if result["padding_used"]:
                padded_valid_events.append(event["timestamp_s"])
            valid_hit_actor_ids.update(
                hit["actor_index"] for hit in result["hits"]
            )
    if padded_valid_events:
        raise ValueError(
            "A supposedly horizon-valid TTC event used actor-state padding."
        )

    cross_modal_summary = load_json(
        cross_modal_report / "multicar_summary.json"
    )
    if (
        Path(cross_modal_summary["baseline_run"]).resolve() != baseline
        or Path(cross_modal_summary["treatment_run"]).resolve() != near
    ):
        raise ValueError(
            "Cross-modal report does not reference this baseline/treatment pair."
        )
    if (
        cross_modal_summary["control"]["pairing_validation"]["status"]
        != "passed"
    ):
        raise ValueError("Cross-modal report pairing validation did not pass.")
    selected_valid_frames = [
        item
        for item in cross_modal_summary["front_frame_evidence"]
        if float(item["timestamp"]) <= valid_end_s + 1e-9
        and item["injected_car_semantic_pixels"] > 0
    ]
    rgb_support = [
        float(item["car_mask_supported_by_rgb_fraction"])
        for item in selected_valid_frames
        if item["car_mask_supported_by_rgb_fraction"] is not None
    ]
    depth_support = [
        float(item["car_mask_supported_by_depth_fraction"])
        for item in selected_valid_frames
        if item["car_mask_supported_by_depth_fraction"] is not None
    ]

    actual_collision = any(
        bool(info.get("collision", False)) for info in infos["near_cut_in"]
    )
    near_clearance = clearances["actors"][0]["minimum_clearance_m"]
    if actual_collision:
        raise ValueError("Near cut-in contains an actual runtime collision.")
    if not (0.0 < near_clearance <= 1.0):
        raise ValueError(
            "Near cut-in does not form the pre-specified positive-clearance "
            "close pass."
        )
    if crossing_s is None or crossing_s > 4.25:
        raise ValueError(
            "Cut-in actor did not cross the centerline by the pre-specified limit."
        )
    if not valid_failed_events or valid_hit_actor_ids != {0}:
        raise ValueError(
            "Horizon-valid TTC failures are missing or not actor0-specific."
        )
    for key in ("baseline", "far_cut_in_control"):
        if valid_windows[key]["first_failure_s"]["ttc"] is not None:
            raise ValueError(f"{key} unexpectedly fails horizon-valid TTC.")
    if valid_windows["near_cut_in"]["first_failure_s"]["ttc"] is None:
        raise ValueError("Near cut-in has no horizon-valid TTC response.")
    if any(
        summary["first_failure_s"]["nc"] is not None
        for summary in valid_windows.values()
    ):
        raise ValueError("At least one condition fails horizon-valid NC.")

    output.mkdir(parents=True, exist_ok=False)
    plot_path = output / "near_cutin_risk_and_clearance.png"
    make_near_cutin_plot(
        plot_path,
        evals["baseline"],
        evals["far_cut_in_control"],
        evals["near_cut_in"],
        infos["near_cut_in"],
        valid_end_s,
        invalid_start_s,
        clearances,
        crossing_s,
    )

    summary = {
        "experiment": (
            "scene-0383 pre-specified single-shot near-distance cut-in"
        ),
        "runs": {key: str(path) for key, path in paths.items()},
        "cross_modal_report": str(cross_modal_report),
        "pairing": pairing,
        "horizon": {
            "planned_waypoints": len(frames[0]["planned_traj"]["traj"]),
            "planned_timestep_s": float(
                frames[0]["planned_traj"]["timestep"]
            ),
            "required_future_actor_history_s": planned_horizon_s,
            "final_timestamp_s": final_timestamp_s,
            "valid_end_s": valid_end_s,
            "invalid_tail_start_s": invalid_start_s,
        },
        "horizon_valid_metrics": valid_windows,
        "event": {
            "cut_in_centerline_crossing_s": crossing_s,
            "actual_collision_observed": actual_collision,
            "minimum_cut_in_2d_oriented_footprint_clearance_m": near_clearance,
            "minimum_cut_in_clearance_timestamp_s": clearances["actors"][0][
                "minimum_clearance_timestamp_s"
            ],
            "first_horizon_valid_ttc_failure_s": valid_windows["near_cut_in"][
                "first_failure_s"
            ]["ttc"],
            "first_horizon_valid_nc_failure_s": valid_windows["near_cut_in"][
                "first_failure_s"
            ]["nc"],
            "valid_failed_event_count": len(valid_failed_events),
            "valid_failed_event_hit_actor_ids": sorted(valid_hit_actor_ids),
            "valid_failed_events_used_padding": False,
        },
        "cross_modal_internal_support": {
            "selected_valid_frame_count": len(selected_valid_frames),
            "car_mask_supported_by_rgb_fraction_range": [
                min(rgb_support),
                max(rgb_support),
            ],
            "car_mask_supported_by_depth_fraction_range": [
                min(depth_support),
                max(depth_support),
            ],
            "guardrail": (
                "RGB, semantic, and depth co-movement is internal "
                "cross-modal evidence because all modalities share one renderer."
            ),
        },
        "decisions": {
            "strict_pairing": "accepted",
            "continuous_actor_state_and_centerline_crossing": "accepted",
            "positive_clearance_internal_close_pass": "accepted",
            "horizon_valid_ttc_response_attributed_to_actor0": "accepted",
            "internal_rgb_semantic_depth_co_movement": "accepted",
            "full_run_aggregate_without_tail_filter": "down-weighted",
            "scripted_merge_realism": "down-weighted",
            "sensor_evidence_for_e2e_evaluation": "down-weighted",
            "actual_collision": "rejected",
            "ad_agent_response": "rejected",
            "global_hugsim_credibility": "rejected",
        },
        "overall_decision": "down-weighted",
        "interpretation": (
            "Unlike the earlier far cut-in, this pre-specified single-shot "
            "near cut-in "
            "creates a positive-clearance close pass and a large TTC response "
            "inside the complete-future-history window. The response is "
            "actor0-specific and uses no tail padding. It validates a narrow "
            "internal metric-response subclaim, not traffic realism, sensor "
            "truth, AD-agent behavior, or global simulator credibility."
        ),
        "visual_artifacts": {
            "risk_and_clearance": str(plot_path),
            "cross_modal_contact_sheet": str(
                cross_modal_report / "front_multicar_contact_sheet.png"
            ),
            "front_video": str(
                cross_modal_report / "front_multicar_comparison.mp4"
            ),
        },
    }
    with (output / "near_cutin_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(jsonable(summary), stream, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
