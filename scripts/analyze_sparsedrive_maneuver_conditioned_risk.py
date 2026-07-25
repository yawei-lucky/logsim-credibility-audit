#!/usr/bin/env python3
"""Refine SparseDrive counterfactual response into maneuver-aware diagnostics.

This analysis does not replace the preregistered same-window decision. It
decomposes the already observed selected-plan response into:

1. route-relative progress changes within fixed native candidate modes;
2. the additional effect of selecting a different native mode;
3. current-frame plan-centreline clearance to the declared actor footprint.

The third component is deliberately a current-state geometry diagnostic, not
physical TTC, collision clearance, or a future actor interaction model.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from make_hugsim_lead_counterfactual_metadata import model_to_world
from render_hugsim_exact_source_pose import sha256_file


PLAN_SHAPE = (3, 6, 6, 2)
SCORE_SHAPE = (3, 6)
FINAL_PLAN_SHAPE = (6, 2)
NUMERIC_TOLERANCE = 1e-7


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--same-window-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def checked_path(record: dict[str, Any]) -> Path:
    path = Path(record["path"]).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if sha256_file(path) != record["sha256"]:
        raise ValueError(f"input hash changed: {path}")
    return path


def checked_native_path(report: dict[str, Any]) -> Path:
    record = report["artifacts"]
    path = Path(record["native_outputs"]).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if sha256_file(path) != record["native_outputs_sha256"]:
        raise ValueError(f"native-output hash changed: {path}")
    return path


def numpy_tensor(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value, dtype=np.float64)


def native_arrays(output: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    planning = numpy_tensor(output["planning"])
    scores = numpy_tensor(output["planning_score"])
    final = numpy_tensor(output["final_planning"])
    if planning.shape != PLAN_SHAPE or not np.isfinite(planning).all():
        raise ValueError("native candidate planning must be one finite 3x6x6x2 tensor")
    if scores.shape != SCORE_SHAPE or not np.isfinite(scores).all():
        raise ValueError("native planning scores must be one finite 3x6 tensor")
    if final.shape != FINAL_PLAN_SHAPE or not np.isfinite(final).all():
        raise ValueError("native final plan must be one finite 6x2 tensor")
    return planning, scores, final


def report_frame_lookup(report: dict[str, Any]) -> dict[int, tuple[int, dict[str, Any]]]:
    result = {}
    for position, frame in enumerate(report["baseline"]["frames"]):
        index = int(frame["source_frame_index"])
        if index in result:
            raise ValueError(f"duplicate source frame in report: {index}")
        result[index] = (position, frame)
    return result


def repeat_envelopes(
    native: dict[str, dict[str, list[dict[str, Any]]]],
    frame_positions: dict[str, dict[int, int]],
    warmed_indices: list[int],
) -> dict[str, Any]:
    by_condition = {}
    for label, runs in native.items():
        score_max = 0.0
        candidate_forward_max = 0.0
        candidate_xy_max = 0.0
        for frame_index in warmed_indices:
            position = frame_positions[label][frame_index]
            planning_a, scores_a, _ = native_arrays(runs["baseline"][position])
            planning_b, scores_b, _ = native_arrays(
                runs["baseline_repeat"][position]
            )
            score_max = max(score_max, float(np.max(np.abs(scores_a - scores_b))))
            candidate_forward_max = max(
                candidate_forward_max,
                float(
                    np.max(
                        np.abs(
                            planning_a[:, :, -1, 1]
                            - planning_b[:, :, -1, 1]
                        )
                    )
                ),
            )
            candidate_xy_max = max(
                candidate_xy_max,
                float(np.max(np.abs(planning_a - planning_b))),
            )
        by_condition[label] = {
            "planning_score_max_abs": score_max,
            "candidate_final_forward_max_abs_m": candidate_forward_max,
            "candidate_plan_xy_max_abs_m": candidate_xy_max,
        }
    return {
        "by_condition": by_condition,
        "planning_score_max_abs": max(
            item["planning_score_max_abs"] for item in by_condition.values()
        ),
        "candidate_final_forward_max_abs_m": max(
            item["candidate_final_forward_max_abs_m"]
            for item in by_condition.values()
        ),
        "candidate_plan_xy_max_abs_m": max(
            item["candidate_plan_xy_max_abs_m"]
            for item in by_condition.values()
        ),
    }


def actor_relative_box(
    manifest: dict[str, Any],
    source_metadata: dict[str, Any],
    label: str,
    frame_index: int,
    front_model_to_camera: np.ndarray,
) -> dict[str, Any]:
    model_pose = model_to_world(
        source_metadata,
        frame_index,
        front_model_to_camera,
    )
    actor_world = np.asarray(
        manifest["conditions"][label]["actor_world_transform_by_frame"][
            str(frame_index)
        ],
        dtype=np.float64,
    )
    relative = np.linalg.inv(model_pose) @ actor_world
    center = relative[:2, 3]
    longitudinal = relative[:2, 0]
    lateral = relative[:2, 2]
    longitudinal_norm = float(np.linalg.norm(longitudinal))
    lateral_norm = float(np.linalg.norm(lateral))
    if min(longitudinal_norm, lateral_norm) < 1e-8:
        raise ValueError("actor footprint axes are degenerate")
    longitudinal /= longitudinal_norm
    lateral /= lateral_norm
    projected_axis_dot = float(np.dot(longitudinal, lateral))
    if abs(projected_axis_dot) > 1e-2:
        raise ValueError("projected actor footprint axes are not near-orthogonal")
    # The 3D axes are rigid and orthogonal. Their ground-plane projections
    # differ by up to roughly 0.002 in dot product because the source rig has
    # pitch/roll. Re-orthogonalize the 2D footprint while preserving the
    # declared lateral-axis sign.
    orthogonal_lateral = np.asarray(
        [-longitudinal[1], longitudinal[0]],
        dtype=np.float64,
    )
    if float(np.dot(orthogonal_lateral, lateral)) < 0:
        orthogonal_lateral *= -1.0
    lateral = orthogonal_lateral

    width, length, _ = (
        float(value) for value in manifest["actor"]["dimensions_wlh_m"]
    )
    half_length = 0.5 * length
    half_width = 0.5 * width
    corners = np.asarray(
        [
            center + half_length * longitudinal + half_width * lateral,
            center + half_length * longitudinal - half_width * lateral,
            center - half_length * longitudinal - half_width * lateral,
            center - half_length * longitudinal + half_width * lateral,
        ],
        dtype=np.float64,
    )

    declared = next(
        item
        for item in manifest["conditions"][label]["actor_relative_geometry"]
        if int(item["source_frame_index"]) == frame_index
    )
    declared_center = np.asarray(
        [declared["right_m"], declared["forward_m"]],
        dtype=np.float64,
    )
    residual = float(np.max(np.abs(center - declared_center)))
    if residual > 1e-6:
        raise ValueError("actor transform and declared relative centre disagree")
    return {
        "center_xy_m": center,
        "longitudinal_unit_xy": longitudinal,
        "lateral_unit_xy": lateral,
        "corners_xy_m": corners,
        "projected_axis_dot_before_orthogonalization": projected_axis_dot,
        "transform_center_residual_m": residual,
    }


def cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def point_in_convex_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    signs = []
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
        signs.append(cross_2d(end - start, point - start))
    return min(signs) >= -1e-10 or max(signs) <= 1e-10


def point_segment_distance(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> float:
    delta = end - start
    denominator = float(np.dot(delta, delta))
    if denominator <= 1e-20:
        return float(np.linalg.norm(point - start))
    fraction = float(np.dot(point - start, delta) / denominator)
    fraction = min(1.0, max(0.0, fraction))
    projection = start + fraction * delta
    return float(np.linalg.norm(point - projection))


def segments_intersect(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> bool:
    first_delta = first_end - first_start
    second_delta = second_end - second_start
    denominator = cross_2d(first_delta, second_delta)
    offset = second_start - first_start
    if abs(denominator) <= 1e-12:
        if abs(cross_2d(offset, first_delta)) > 1e-10:
            return False
        return (
            point_segment_distance(first_start, second_start, second_end) <= 1e-10
            or point_segment_distance(first_end, second_start, second_end) <= 1e-10
            or point_segment_distance(second_start, first_start, first_end) <= 1e-10
            or point_segment_distance(second_end, first_start, first_end) <= 1e-10
        )
    first_fraction = cross_2d(offset, second_delta) / denominator
    second_fraction = cross_2d(offset, first_delta) / denominator
    return (
        -1e-10 <= first_fraction <= 1.0 + 1e-10
        and -1e-10 <= second_fraction <= 1.0 + 1e-10
    )


def segment_distance(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> float:
    if segments_intersect(first_start, first_end, second_start, second_end):
        return 0.0
    return min(
        point_segment_distance(first_start, second_start, second_end),
        point_segment_distance(first_end, second_start, second_end),
        point_segment_distance(second_start, first_start, first_end),
        point_segment_distance(second_end, first_start, first_end),
    )


def polyline_box_clearance(plan_xy: np.ndarray, corners_xy: np.ndarray) -> float:
    plan = np.asarray(plan_xy, dtype=np.float64)
    corners = np.asarray(corners_xy, dtype=np.float64)
    if plan.shape != FINAL_PLAN_SHAPE or corners.shape != (4, 2):
        raise ValueError("clearance expects one 6x2 plan and four box corners")
    points = np.vstack((np.zeros((1, 2), dtype=np.float64), plan))
    if any(point_in_convex_polygon(point, corners) for point in points):
        return 0.0
    minimum = math.inf
    for first_start, first_end in zip(points[:-1], points[1:], strict=True):
        for second_start, second_end in zip(
            corners,
            np.roll(corners, -1, axis=0),
            strict=True,
        ):
            minimum = min(
                minimum,
                segment_distance(
                    first_start,
                    first_end,
                    second_start,
                    second_end,
                ),
            )
    return float(minimum)


def classify_response(
    selected_delta_m: float,
    candidate_deltas_m: np.ndarray,
    mode_changed: bool,
    selected_repeat_envelope_m: float,
    candidate_repeat_envelope_m: float,
) -> str:
    candidate_deltas = np.asarray(candidate_deltas_m, dtype=np.float64)
    all_less = bool(np.max(candidate_deltas) < -candidate_repeat_envelope_m)
    all_more = bool(np.min(candidate_deltas) > candidate_repeat_envelope_m)
    selected_less = selected_delta_m < -selected_repeat_envelope_m
    selected_more = selected_delta_m > selected_repeat_envelope_m
    if mode_changed and all_less and selected_more:
        return "mode_switch_masks_candidate_consensus_less_progress"
    if mode_changed and all_less and selected_less:
        return "mode_switch_with_candidate_consensus_less_progress"
    if not mode_changed and all_less and selected_less:
        return "same_mode_candidate_consensus_less_progress"
    if not mode_changed and all_more and selected_more:
        return "same_mode_candidate_consensus_more_progress_reversal"
    if mode_changed:
        return "mode_switch_with_mixed_candidate_response"
    return "same_mode_with_mixed_candidate_response"


def top_two(scores: np.ndarray) -> tuple[int, float, int, float, float]:
    order = np.argsort(scores)[::-1]
    first = int(order[0])
    second = int(order[1])
    return (
        first,
        float(scores[first]),
        second,
        float(scores[second]),
        float(scores[first] - scores[second]),
    )


def analyze_rows(
    audit: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    native: dict[str, dict[str, list[dict[str, Any]]]],
    manifest: dict[str, Any],
    source_metadata: dict[str, Any],
    repeat: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    labels = ("real", "factual", "weak", "strong")
    lookups = {label: report_frame_lookup(reports[label]) for label in labels}
    warmed_indices = [
        int(row["source_frame_index"]) for row in audit["fully_warmed_rows"]
    ]
    selected_repeat = float(audit["repeat_final_forward_envelope"]["maximum_m"])
    candidate_repeat = float(repeat["candidate_final_forward_max_abs_m"])
    domain_scale = max(
        abs(float(row["D_domain_forward_sim_minus_real_m"]))
        for row in audit["fully_warmed_rows"]
    )
    rows = []
    for source_row in audit["fully_warmed_rows"]:
        frame_index = int(source_row["source_frame_index"])
        condition = {}
        report_frames = {}
        for label in labels:
            position, report_frame = lookups[label][frame_index]
            report_frames[label] = report_frame
            planning, scores, final = native_arrays(
                native[label]["baseline"][position]
            )
            command = int(
                report_frame["planning_selection"][
                    "command_index_right_left_straight"
                ]
            )
            selected_mode = int(
                report_frame["planning_selection"]["selected_mode_index"]
            )
            score_mode = int(np.argmax(scores[command]))
            if score_mode != selected_mode:
                raise ValueError(f"{label} frame {frame_index}: mode/score mismatch")
            selected_candidate = planning[command, selected_mode]
            selected_residual = float(
                np.max(np.abs(final - selected_candidate))
            )
            if selected_residual > NUMERIC_TOLERANCE:
                raise ValueError(
                    f"{label} frame {frame_index}: final plan is not selected candidate"
                )
            if selected_mode != int(source_row["selected_mode"][label]):
                raise ValueError(
                    f"{label} frame {frame_index}: audit mode mismatch"
                )
            score_summary = top_two(scores[command])
            condition[label] = {
                "planning": planning,
                "scores": scores,
                "final": final,
                "command": command,
                "mode": selected_mode,
                "selected_candidate_residual_m": selected_residual,
                "top_mode": score_summary[0],
                "top_score": score_summary[1],
                "runner_up_mode": score_summary[2],
                "runner_up_score": score_summary[3],
                "selection_margin": score_summary[4],
            }

        commands = {condition[label]["command"] for label in labels}
        if len(commands) != 1:
            raise ValueError(f"frame {frame_index}: held-fixed command differs")
        command = next(iter(commands))
        weak = condition["weak"]
        strong = condition["strong"]
        candidate_deltas = (
            strong["planning"][command, :, -1, 1]
            - weak["planning"][command, :, -1, 1]
        )
        selected_delta = float(strong["final"][-1, 1] - weak["final"][-1, 1])
        weak_mode = int(weak["mode"])
        strong_mode = int(strong["mode"])
        fixed_weak_mode_delta = float(candidate_deltas[weak_mode])
        selection_contribution = float(
            strong["planning"][command, strong_mode, -1, 1]
            - strong["planning"][command, weak_mode, -1, 1]
        )
        decomposition_residual = abs(
            selected_delta - fixed_weak_mode_delta - selection_contribution
        )
        if decomposition_residual > NUMERIC_TOLERANCE:
            raise ValueError(f"frame {frame_index}: response decomposition failed")

        front_model_to_camera = np.asarray(
            report_frames["weak"]["input_contract"]["front_model_to_camera"],
            dtype=np.float64,
        )
        weak_box = actor_relative_box(
            manifest,
            source_metadata,
            "weak",
            frame_index,
            front_model_to_camera,
        )
        strong_box = actor_relative_box(
            manifest,
            source_metadata,
            "strong",
            frame_index,
            front_model_to_camera,
        )
        weak_clearance = polyline_box_clearance(
            weak["final"],
            weak_box["corners_xy_m"],
        )
        strong_clearance = polyline_box_clearance(
            strong["final"],
            strong_box["corners_xy_m"],
        )
        strong_fixed_weak_mode_clearance = polyline_box_clearance(
            strong["planning"][command, weak_mode],
            strong_box["corners_xy_m"],
        )

        all_less = bool(np.max(candidate_deltas) < -candidate_repeat)
        all_more = bool(np.min(candidate_deltas) > candidate_repeat)
        all_candidate_effects_exceed_domain = bool(
            np.min(np.abs(candidate_deltas)) > domain_scale
        )
        row = {
            "source_frame_index": frame_index,
            "timestamp_s": float(source_row["timestamp_s"]),
            "command_index_right_left_straight": command,
            "selected_mode": {"weak": weak_mode, "strong": strong_mode},
            "selected_mode_changed": weak_mode != strong_mode,
            "selected_mode_margin": {
                label: float(condition[label]["selection_margin"])
                for label in ("weak", "strong")
            },
            "selected_mode_margin_exceeds_repeat_score_envelope": {
                label: bool(
                    condition[label]["selection_margin"]
                    > repeat["planning_score_max_abs"]
                )
                for label in ("weak", "strong")
            },
            "selected_strong_minus_weak_final_forward_m": selected_delta,
            "same_mode_candidate_strong_minus_weak_final_forward_m": (
                candidate_deltas.astype(float).tolist()
            ),
            "same_mode_candidate_consensus": (
                "strong_less_progress"
                if all_less
                else "strong_more_progress"
                if all_more
                else "mixed"
            ),
            "fixed_weak_mode_response_m": fixed_weak_mode_delta,
            "strong_condition_mode_selection_contribution_m": (
                selection_contribution
            ),
            "decomposition_residual_m": decomposition_residual,
            "all_candidate_effects_exceed_observed_domain_scale": (
                all_candidate_effects_exceed_domain
            ),
            "response_class": classify_response(
                selected_delta,
                candidate_deltas,
                weak_mode != strong_mode,
                selected_repeat,
                candidate_repeat,
            ),
            "current_actor_geometry": {
                "weak_center_xy_m": (
                    weak_box["center_xy_m"].astype(float).tolist()
                ),
                "strong_center_xy_m": (
                    strong_box["center_xy_m"].astype(float).tolist()
                ),
                "weak_selected_plan_centreline_to_current_actor_footprint_m": (
                    weak_clearance
                ),
                "strong_selected_plan_centreline_to_current_actor_footprint_m": (
                    strong_clearance
                ),
                "strong_fixed_weak_mode_centreline_to_current_actor_footprint_m": (
                    strong_fixed_weak_mode_clearance
                ),
                "strong_mode_selection_clearance_change_m": float(
                    strong_clearance - strong_fixed_weak_mode_clearance
                ),
                "construct_boundary": (
                    "current-frame planned centreline to simulator-declared "
                    "actor footprint; excludes ego footprint, future actor "
                    "motion, physical TTC and collision"
                ),
            },
        }
        rows.append(row)

    summary = {
        "fully_warmed_frame_count": len(rows),
        "selected_strong_less_progress_count": sum(
            row["selected_strong_minus_weak_final_forward_m"]
            < -selected_repeat
            for row in rows
        ),
        "selected_strong_more_progress_reversal_count": sum(
            row["selected_strong_minus_weak_final_forward_m"]
            > selected_repeat
            for row in rows
        ),
        "selected_mode_switch_count": sum(
            row["selected_mode_changed"] for row in rows
        ),
        "candidate_consensus_strong_less_progress_count": sum(
            row["same_mode_candidate_consensus"] == "strong_less_progress"
            for row in rows
        ),
        "candidate_consensus_strong_more_progress_reversal_count": sum(
            row["same_mode_candidate_consensus"] == "strong_more_progress"
            for row in rows
        ),
        "candidate_consensus_effect_exceeds_observed_domain_scale_count": sum(
            row["all_candidate_effects_exceed_observed_domain_scale"]
            for row in rows
        ),
        "mode_switch_masks_candidate_consensus_frames": [
            row["source_frame_index"]
            for row in rows
            if row["response_class"]
            == "mode_switch_masks_candidate_consensus_less_progress"
        ],
        "same_mode_candidate_consensus_reversal_frames": [
            row["source_frame_index"]
            for row in rows
            if row["response_class"]
            == "same_mode_candidate_consensus_more_progress_reversal"
        ],
        "strong_selected_current_actor_clearance_zero_count": sum(
            row["current_actor_geometry"][
                "strong_selected_plan_centreline_to_current_actor_footprint_m"
            ]
            <= 1e-10
            for row in rows
        ),
    }
    return rows, summary


def save_csv(rows: list[dict[str, Any]], output: Path) -> Path:
    path = output / "maneuver_conditioned_risk_decomposition.csv"
    fields = [
        "source_frame_index",
        "command",
        "weak_mode",
        "strong_mode",
        "mode_changed",
        "selected_delta_forward_m",
        "fixed_weak_mode_delta_forward_m",
        "mode_selection_contribution_m",
        "candidate_min_delta_forward_m",
        "candidate_max_delta_forward_m",
        "candidate_consensus",
        "weak_selection_margin",
        "strong_selection_margin",
        "weak_current_actor_clearance_m",
        "strong_current_actor_clearance_m",
        "strong_fixed_weak_mode_clearance_m",
        "response_class",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            candidate = row[
                "same_mode_candidate_strong_minus_weak_final_forward_m"
            ]
            geometry = row["current_actor_geometry"]
            writer.writerow(
                {
                    "source_frame_index": row["source_frame_index"],
                    "command": row["command_index_right_left_straight"],
                    "weak_mode": row["selected_mode"]["weak"],
                    "strong_mode": row["selected_mode"]["strong"],
                    "mode_changed": row["selected_mode_changed"],
                    "selected_delta_forward_m": (
                        row["selected_strong_minus_weak_final_forward_m"]
                    ),
                    "fixed_weak_mode_delta_forward_m": (
                        row["fixed_weak_mode_response_m"]
                    ),
                    "mode_selection_contribution_m": (
                        row["strong_condition_mode_selection_contribution_m"]
                    ),
                    "candidate_min_delta_forward_m": min(candidate),
                    "candidate_max_delta_forward_m": max(candidate),
                    "candidate_consensus": row["same_mode_candidate_consensus"],
                    "weak_selection_margin": (
                        row["selected_mode_margin"]["weak"]
                    ),
                    "strong_selection_margin": (
                        row["selected_mode_margin"]["strong"]
                    ),
                    "weak_current_actor_clearance_m": geometry[
                        "weak_selected_plan_centreline_to_current_actor_footprint_m"
                    ],
                    "strong_current_actor_clearance_m": geometry[
                        "strong_selected_plan_centreline_to_current_actor_footprint_m"
                    ],
                    "strong_fixed_weak_mode_clearance_m": geometry[
                        "strong_fixed_weak_mode_centreline_to_current_actor_footprint_m"
                    ],
                    "response_class": row["response_class"],
                }
            )
    return path


def save_visualization(
    rows: list[dict[str, Any]],
    selected_repeat_m: float,
    candidate_repeat_m: float,
    domain_scale_m: float,
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    frames = [row["source_frame_index"] for row in rows]
    candidate = np.asarray(
        [
            row["same_mode_candidate_strong_minus_weak_final_forward_m"]
            for row in rows
        ],
        dtype=np.float64,
    )
    selected = np.asarray(
        [row["selected_strong_minus_weak_final_forward_m"] for row in rows],
        dtype=np.float64,
    )
    fixed = np.asarray(
        [row["fixed_weak_mode_response_m"] for row in rows],
        dtype=np.float64,
    )
    selection = np.asarray(
        [
            row["strong_condition_mode_selection_contribution_m"]
            for row in rows
        ],
        dtype=np.float64,
    )
    weak_clearance = np.asarray(
        [
            row["current_actor_geometry"][
                "weak_selected_plan_centreline_to_current_actor_footprint_m"
            ]
            for row in rows
        ]
    )
    strong_clearance = np.asarray(
        [
            row["current_actor_geometry"][
                "strong_selected_plan_centreline_to_current_actor_footprint_m"
            ]
            for row in rows
        ]
    )
    strong_fixed_clearance = np.asarray(
        [
            row["current_actor_geometry"][
                "strong_fixed_weak_mode_centreline_to_current_actor_footprint_m"
            ]
            for row in rows
        ]
    )

    figure, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    colors = ["#2ca02c" if value < 0 else "#d62728" for value in selected]
    axes[0, 0].bar([str(frame) for frame in frames], selected, color=colors)
    axes[0, 0].axhspan(
        -selected_repeat_m,
        selected_repeat_m,
        color="#7f7f7f",
        alpha=0.35,
        label=f"repeat ±{selected_repeat_m:.6f} m",
    )
    axes[0, 0].axhline(domain_scale_m, color="#9467bd", linestyle="--")
    axes[0, 0].axhline(-domain_scale_m, color="#9467bd", linestyle="--")
    axes[0, 0].axhline(0.0, color="black", linewidth=1)
    axes[0, 0].set(
        title="Selected plan: strong − weak route progress",
        xlabel="source frame",
        ylabel="3 s endpoint forward difference (m)",
    )
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].grid(axis="y", alpha=0.25)

    limit = float(np.max(np.abs(candidate)))
    image = axes[0, 1].imshow(
        candidate.T,
        aspect="auto",
        cmap="RdBu_r",
        vmin=-limit,
        vmax=limit,
    )
    axes[0, 1].set(
        title=(
            "Fixed-mode candidate response\n"
            f"(repeat envelope {candidate_repeat_m:.6f} m)"
        ),
        xlabel="source frame",
        ylabel="native candidate mode",
        xticks=np.arange(len(frames)),
        xticklabels=frames,
        yticks=np.arange(candidate.shape[1]),
    )
    for row_index in range(candidate.shape[1]):
        for column in range(candidate.shape[0]):
            value = candidate[column, row_index]
            axes[0, 1].text(
                column,
                row_index,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if abs(value) > 0.45 * limit else "black",
            )
    figure.colorbar(image, ax=axes[0, 1], label="strong − weak forward (m)")

    x = np.arange(len(frames))
    axes[1, 0].bar(
        x,
        fixed,
        width=0.65,
        color="#1f77b4",
        label="fixed weak-selected mode response",
    )
    axes[1, 0].bar(
        x,
        selection,
        width=0.65,
        bottom=fixed,
        color="#ff7f0e",
        label="strong-condition mode-selection contribution",
    )
    axes[1, 0].plot(
        x,
        selected,
        color="black",
        marker="o",
        linewidth=1.8,
        label="reconstructed selected response",
    )
    axes[1, 0].axhline(0.0, color="black", linewidth=1)
    axes[1, 0].set(
        title="Selected response decomposition",
        xlabel="source frame",
        ylabel="forward difference (m)",
        xticks=x,
        xticklabels=frames,
    )
    axes[1, 0].legend(fontsize=8)
    axes[1, 0].grid(axis="y", alpha=0.25)

    axes[1, 1].plot(
        frames,
        weak_clearance,
        marker="o",
        linewidth=2,
        label="weak selected plan → weak actor",
    )
    axes[1, 1].plot(
        frames,
        strong_clearance,
        marker="o",
        linewidth=2,
        label="strong selected plan → strong actor",
    )
    axes[1, 1].plot(
        frames,
        strong_fixed_clearance,
        marker="x",
        linestyle="--",
        linewidth=2,
        label="strong weak-mode plan → strong actor",
    )
    axes[1, 1].set(
        title="Current actor-footprint centreline clearance (diagnostic only)",
        xlabel="source frame",
        ylabel="metres",
    )
    axes[1, 1].legend(fontsize=8)
    axes[1, 1].grid(alpha=0.25)

    figure.suptitle(
        "Prospective maneuver-conditioned SparseDrive response audit\n"
        "No scalar credibility score; original preregistered 3/5 rejection remains",
        fontsize=15,
    )
    path = output / "maneuver_conditioned_risk_decomposition.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    audit_path = args.same_window_audit.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not audit_path.is_file():
        raise FileNotFoundError(audit_path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")

    audit = load_json(audit_path)
    reports = {
        label: load_json(checked_path(audit["inputs"][label]))
        for label in ("real", "factual", "weak", "strong")
    }
    manifest_path = checked_path(audit["counterfactual_manifest"])
    manifest = load_json(manifest_path)
    source_metadata_path = Path(manifest["source_metadata"]).expanduser().resolve()
    if (
        not source_metadata_path.is_file()
        or sha256_file(source_metadata_path) != manifest["source_metadata_sha256"]
    ):
        raise ValueError("source metadata is absent or changed")
    source_metadata = load_json(source_metadata_path)

    import torch

    native = {}
    frame_positions = {}
    for label, report in reports.items():
        loaded = torch.load(checked_native_path(report), map_location="cpu")
        if set(loaded) != {"baseline", "baseline_repeat"}:
            raise ValueError(f"{label}: native output run keys changed")
        native[label] = loaded
        lookup = report_frame_lookup(report)
        frame_positions[label] = {
            frame_index: position for frame_index, (position, _) in lookup.items()
        }

    warmed_indices = [
        int(row["source_frame_index"]) for row in audit["fully_warmed_rows"]
    ]
    repeat = repeat_envelopes(native, frame_positions, warmed_indices)
    rows, summary = analyze_rows(
        audit,
        reports,
        native,
        manifest,
        source_metadata,
        repeat,
    )

    output.mkdir(parents=True)
    csv_path = save_csv(rows, output)
    domain_scale = max(
        abs(float(row["D_domain_forward_sim_minus_real_m"]))
        for row in audit["fully_warmed_rows"]
    )
    plot_path = save_visualization(
        rows,
        float(audit["repeat_final_forward_envelope"]["maximum_m"]),
        float(repeat["candidate_final_forward_max_abs_m"]),
        domain_scale,
        output,
    )
    result = {
        "audit_id": "sparsedrive_maneuver_conditioned_risk_001",
        "date": date.today().isoformat(),
        "purpose": (
            "prospective refinement of a rejected maneuver-independent "
            "longitudinal indicator using existing evidence only"
        ),
        "inputs": {
            "same_window_audit": {
                "path": str(audit_path),
                "sha256": sha256_file(audit_path),
            },
            "counterfactual_manifest": {
                "path": str(manifest_path),
                "sha256": sha256_file(manifest_path),
            },
            "receiver_reports_and_native_outputs": {
                label: {
                    "report": audit["inputs"][label],
                    "native_outputs": {
                        "path": str(checked_native_path(reports[label])),
                        "sha256": reports[label]["artifacts"][
                            "native_outputs_sha256"
                        ],
                    },
                }
                for label in reports
            },
        },
        "indicator_definition": {
            "form": "non-compensatory response vector; no scalar risk score",
            "components": [
                "selected native mode identity and score margin",
                "selected-plan route-relative 3 s endpoint progress",
                "strong-minus-weak progress for each of six fixed native modes",
                "mode-selection contribution to the selected response",
                (
                    "selected plan-centreline distance to the current "
                    "simulator-declared actor footprint"
                ),
            ],
            "interpretation_rule": (
                "interpret longitudinal direction only with native-mode "
                "identity and fixed-mode decomposition; retain unresolved "
                "reversals instead of compensating them with a weighted score"
            ),
        },
        "qualification_gates": {
            "held_fixed_gate_in_source_audit": audit["held_fixed_gate"],
            "native_final_plan_equals_selected_candidate": True,
            "same_command_within_each_timestamp": True,
            "actor_transform_matches_declared_relative_geometry": True,
            "decomposition_reconstructs_selected_response": True,
        },
        "uncertainty_references": {
            "selected_plan_repeat_final_forward_envelope_m": audit[
                "repeat_final_forward_envelope"
            ],
            "native_candidate_and_score_repeat_envelopes": repeat,
            "observed_factual_real_forward_domain_max_abs_m": domain_scale,
            "domain_boundary": (
                "empirical scale from one matched slice, not an externally "
                "qualified acceptance threshold"
            ),
        },
        "fully_warmed_rows": rows,
        "summary": summary,
        "indicator_qualification_table": [
            {
                "tool": "native candidate-mode and score decomposition",
                "decision": "accepted",
                "measures": (
                    "whether an endpoint reversal originates within fixed "
                    "candidate modes or from native mode selection"
                ),
                "independence": (
                    "does not use HUGSIM scorer; depends on the frozen "
                    "SparseDrive receiver and its HUGSIM RGB input"
                ),
                "strongest_allowed_claim": (
                    "diagnose selected-plan response composition and selection "
                    "stability relative to local repeat sensitivity"
                ),
                "missing_for_stronger_claim": (
                    "semantic meaning and real-world correctness of candidate "
                    "modes, plus another receiver or external behavior reference"
                ),
            },
            {
                "tool": "route-relative endpoint progress",
                "decision": "down-weighted",
                "measures": "one selected or fixed-mode plan's 3 s route progress",
                "independence": (
                    "receiver output in an audited model coordinate contract; "
                    "not an independent risk label"
                ),
                "strongest_allowed_claim": (
                    "conditional response direction when the compared maneuver "
                    "branch remains explicit and comparable"
                ),
                "missing_for_stronger_claim": (
                    "qualified maneuver semantics, task acceptance range and "
                    "real planning-response reference"
                ),
            },
            {
                "tool": (
                    "current actor-footprint centreline clearance as a "
                    "dynamic-risk indicator"
                ),
                "decision": "rejected",
                "measures": (
                    "spatial proximity of the planned centreline to the current "
                    "declared actor rectangle"
                ),
                "independence": (
                    "calculation is independent of HUGSIM scorer, but actor "
                    "pose and dimensions are HUGSIM experiment metadata"
                ),
                "strongest_allowed_claim": (
                    "none for dynamic risk; retain only as a current-state "
                    "geometric visualization under the declared intervention"
                ),
                "missing_for_stronger_claim": (
                    "ego footprint, complete future actor states, time-aligned "
                    "motion, independent 3D truth and physical collision model"
                ),
            },
            {
                "tool": "native planning-score margin",
                "decision": "accepted",
                "measures": (
                    "local numerical separation between selected and runner-up "
                    "receiver modes"
                ),
                "independence": "SparseDrive-native; independent of HUGSIM scorer",
                "strongest_allowed_claim": (
                    "whether the selected mode margin exceeds measured reset "
                    "repeat sensitivity"
                ),
                "missing_for_stronger_claim": (
                    "score calibration and evidence that margin represents "
                    "driving confidence or safety"
                ),
            },
        ],
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": [
                (
                    "the decomposition exactly reconstructs all five selected "
                    "native responses and separates fixed-mode from mode-selection effects"
                ),
                (
                    "frame 48 is a mode-selection confound: all six fixed modes "
                    "reduce progress while the selected endpoint reverses"
                ),
                (
                    "frame 54 is not explained by mode switching: the selected "
                    "mode is unchanged and all six fixed modes reverse slightly"
                ),
            ],
            "down-weighted": [
                (
                    "frames 30, 36 and 42 show candidate-wide less-progress "
                    "effects larger than the observed one-slice domain scale, "
                    "but there is no external acceptance threshold"
                ),
                (
                    "current actor-footprint clearance is a construct diagnostic "
                    "rather than time-aligned physical risk; it saturates at "
                    "zero in four of five strong-condition frames"
                ),
            ],
            "rejected": [
                (
                    "the original preregistered strong-less-forward criterion "
                    "remains rejected at 3/5 and is not rescored"
                ),
                (
                    "route endpoint alone is a maneuver-independent risk metric"
                ),
                (
                    "the current actor-footprint diagnostic establishes TTC, "
                    "collision, realistic avoidance or AD safety"
                ),
            ],
        },
        "artifacts": {
            "decomposition_csv": {
                "path": str(csv_path),
                "sha256": sha256_file(csv_path),
            },
            "decomposition_plot": {
                "path": str(plot_path),
                "sha256": sha256_file(plot_path),
            },
        },
    }
    result_path = output / "sparsedrive_maneuver_conditioned_risk_audit.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
