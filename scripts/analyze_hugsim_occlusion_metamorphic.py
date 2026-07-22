#!/usr/bin/env python3
"""Analyze the CF-O 001 HUGSIM controlled-occlusion experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_hugsim_horizon_factorial import rectangle
from analyze_hugsim_multicar import paired_differences, validate_run_pairing
from analyze_sparse4d_hugsim_baseline import camera_projection, box_corners, project


CONDITIONS = (
    "no_actor",
    "target_only",
    "partial_occluder_only",
    "partial_both",
    "strong_occluder_only",
    "strong_both",
)
DISPLAY_NAMES = {
    "target_only": "Target only",
    "partial_both": "Partial occlusion",
    "strong_both": "Strong occlusion",
}
ROLE_INDEX = {
    "target_only": {"target": 0},
    "partial_occluder_only": {"occluder": 0},
    "partial_both": {"occluder": 0, "target": 1},
    "strong_occluder_only": {"occluder": 0},
    "strong_both": {"occluder": 0, "target": 1},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_blob(repo_root: Path, commit: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def verify_preregistration_commit(
    repo_root: Path,
    commit: str,
    preregistration_path: Path,
    preregistration: dict[str, Any],
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative_preregistration = str(preregistration_path.relative_to(repo_root))
    if git_blob(repo_root, resolved, relative_preregistration) != preregistration_path.read_bytes():
        raise ValueError("preregistration file differs from preregistration commit")

    script_relative = "scripts/analyze_hugsim_occlusion_metamorphic.py"
    if sha256_bytes(git_blob(repo_root, resolved, script_relative)) != preregistration[
        "analysis_script_sha256"
    ]:
        raise ValueError("analysis script in preregistration commit has wrong hash")
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        if sha256_bytes(git_blob(repo_root, resolved, spec["config"])) != spec[
            "config_sha256"
        ]:
            raise ValueError(f"{condition}: config in preregistration commit has wrong hash")
    return resolved


def actor_box(info: dict[str, Any], index: int) -> np.ndarray:
    boxes = info["obj_boxes"]
    if index >= len(boxes):
        raise ValueError(
            f"timestamp {info['timestamp']}: actor index {index} missing from {len(boxes)} boxes"
        )
    return np.asarray(boxes[index], dtype=np.float64)


def box_in_vehicle_frame(info: dict[str, Any], box: np.ndarray) -> np.ndarray:
    """Transform a HUGSIM global box into the ego/vehicle camera frame."""
    ego = np.asarray(info["ego_box"], dtype=np.float64)
    yaw = float(ego[6])
    cosine, sine = np.cos(yaw), np.sin(yaw)
    delta = box[:3] - ego[:3]
    local = np.asarray(
        [
            cosine * delta[0] + sine * delta[1],
            -sine * delta[0] + cosine * delta[1],
            delta[2],
        ],
        dtype=np.float64,
    )
    local_yaw = float((box[6] - yaw + np.pi) % (2 * np.pi) - np.pi)
    return np.concatenate((local, box[3:6], [local_yaw]))


def projected_mask(
    info: dict[str, Any],
    box: np.ndarray,
    camera: str,
    image_shape: tuple[int, int],
    minimum_depth_m: float,
) -> tuple[np.ndarray, float]:
    projection = camera_projection(info, camera)
    local_box = box_in_vehicle_frame(info, box)
    pixels, corner_depths = project(box_corners(local_box), projection)
    _, center_depths = project(local_box[None, :3], projection)
    center_depth = float(center_depths[0])
    if center_depth <= minimum_depth_m or np.count_nonzero(corner_depths > minimum_depth_m) < 4:
        raise ValueError("actor does not have a valid camera projection")
    hull = cv2.convexHull(np.rint(pixels).astype(np.int32))
    mask = np.zeros(image_shape, dtype=np.uint8)
    cv2.fillConvexPoly(mask, hull, 1)
    return mask.astype(bool), center_depth


def overlap_relation(
    target_mask: np.ndarray,
    partial_occluder_mask: np.ndarray,
    strong_occluder_mask: np.ndarray,
    maximum_partial_outside_strong_target_fraction: float,
) -> dict[str, Any]:
    target_pixels = int(np.count_nonzero(target_mask))
    if target_pixels == 0:
        raise ValueError("projected target mask is empty")
    partial = target_mask & partial_occluder_mask
    strong = target_mask & strong_occluder_mask
    partial_pixels = int(np.count_nonzero(partial))
    strong_pixels = int(np.count_nonzero(strong))
    partial_outside_strong = int(np.count_nonzero(partial & ~strong))
    partial_outside_strong_target_fraction = partial_outside_strong / target_pixels
    partial_fraction = partial_pixels / target_pixels
    strong_fraction = strong_pixels / target_pixels
    passed = (
        partial_outside_strong_target_fraction
        <= maximum_partial_outside_strong_target_fraction
        and strong_fraction > partial_fraction > 0.0
    )
    return {
        "target_projected_pixels": target_pixels,
        "partial_overlap_pixels": partial_pixels,
        "strong_overlap_pixels": strong_pixels,
        "partial_coverage_fraction": partial_fraction,
        "strong_coverage_fraction": strong_fraction,
        "partial_outside_strong_pixels": partial_outside_strong,
        "partial_outside_strong_target_fraction": partial_outside_strong_target_fraction,
        "passed": passed,
    }


def depth_order_passes(
    occluder_depth_m: float, target_depth_m: float, minimum_depth_m: float
) -> bool:
    return minimum_depth_m < occluder_depth_m < target_depth_m


def planar_offset_residual(
    target_box: np.ndarray,
    occluder_box: np.ndarray,
    expected_forward_m: float,
    expected_lateral_m: float,
) -> float:
    observed = target_box[:2] - occluder_box[:2]
    expected = np.asarray([expected_forward_m, expected_lateral_m])
    return float(np.max(np.abs(observed - expected)))


def nested_support_domain(
    target_mask: np.ndarray,
    partial_occluder_mask: np.ndarray,
    strong_occluder_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Exclude partial-only geometry so retained occlusion is monotonically nested."""
    partial_only = target_mask & partial_occluder_mask & ~strong_occluder_mask
    return target_mask & ~partial_only, partial_only


def role_invariance(
    infos: dict[str, list[dict[str, Any]]], tolerance: float
) -> dict[str, Any]:
    comparisons = {
        "target_only_vs_partial_both": ("target_only", 0, "partial_both", 1),
        "target_only_vs_strong_both": ("target_only", 0, "strong_both", 1),
        "partial_occluder_only_vs_partial_both": (
            "partial_occluder_only",
            0,
            "partial_both",
            0,
        ),
        "strong_occluder_only_vs_strong_both": (
            "strong_occluder_only",
            0,
            "strong_both",
            0,
        ),
    }
    results = {}
    for name, (left_name, left_index, right_name, right_index) in comparisons.items():
        left_infos, right_infos = infos[left_name], infos[right_name]
        if len(left_infos) != len(right_infos):
            raise ValueError(f"{name}: state counts differ")
        differences = [
            float(
                np.max(
                    np.abs(
                        actor_box(left, left_index) - actor_box(right, right_index)
                    )
                )
            )
            for left, right in zip(left_infos, right_infos, strict=True)
        ]
        maximum = max(differences, default=0.0)
        results[name] = {
            "maximum_actor_box_absolute_difference": maximum,
            "passed": maximum <= tolerance,
        }
    return {
        "tolerance": tolerance,
        "comparisons": results,
        "passed": all(item["passed"] for item in results.values()),
    }


def geometry_metrics(
    infos: dict[str, list[dict[str, Any]]],
    image_shape: tuple[int, int],
    camera: str,
    minimum_depth_m: float,
    minimum_clearance_m: float,
    maximum_partial_outside_strong_target_fraction: float,
    expected_forward_separation_m: float,
    expected_partial_lateral_separation_m: float,
    expected_strong_lateral_separation_m: float,
    actor_state_tolerance: float,
) -> dict[str, Any]:
    frame_count = len(infos["partial_both"])
    if len(infos["strong_both"]) != frame_count:
        raise ValueError("partial and strong state counts differ")
    rows = []
    for index in range(frame_count):
        partial_info = infos["partial_both"][index]
        strong_info = infos["strong_both"][index]
        partial_target = actor_box(partial_info, ROLE_INDEX["partial_both"]["target"])
        partial_occluder = actor_box(
            partial_info, ROLE_INDEX["partial_both"]["occluder"]
        )
        strong_target = actor_box(strong_info, ROLE_INDEX["strong_both"]["target"])
        strong_occluder = actor_box(
            strong_info, ROLE_INDEX["strong_both"]["occluder"]
        )

        partial_target_mask, partial_target_depth = projected_mask(
            partial_info, partial_target, camera, image_shape, minimum_depth_m
        )
        partial_occluder_mask, partial_occluder_depth = projected_mask(
            partial_info, partial_occluder, camera, image_shape, minimum_depth_m
        )
        strong_target_mask, strong_target_depth = projected_mask(
            strong_info, strong_target, camera, image_shape, minimum_depth_m
        )
        strong_occluder_mask, strong_occluder_depth = projected_mask(
            strong_info, strong_occluder, camera, image_shape, minimum_depth_m
        )
        relation = overlap_relation(
            strong_target_mask,
            partial_occluder_mask,
            strong_occluder_mask,
            maximum_partial_outside_strong_target_fraction,
        )
        target_mask_difference = int(
            np.count_nonzero(partial_target_mask ^ strong_target_mask)
        )
        partial_clearance = float(
            rectangle(partial_target).distance(rectangle(partial_occluder))
        )
        strong_clearance = float(
            rectangle(strong_target).distance(rectangle(strong_occluder))
        )
        partial_offset_residual = planar_offset_residual(
            partial_target,
            partial_occluder,
            expected_forward_separation_m,
            expected_partial_lateral_separation_m,
        )
        strong_offset_residual = planar_offset_residual(
            strong_target,
            strong_occluder,
            expected_forward_separation_m,
            expected_strong_lateral_separation_m,
        )
        offset_passed = (
            partial_offset_residual <= actor_state_tolerance
            and strong_offset_residual <= actor_state_tolerance
        )
        depth_order = depth_order_passes(
            partial_occluder_depth, partial_target_depth, minimum_depth_m
        ) and depth_order_passes(
            strong_occluder_depth, strong_target_depth, minimum_depth_m
        )
        clearance_passed = (
            partial_clearance > minimum_clearance_m
            and strong_clearance > minimum_clearance_m
        )
        passed = (
            relation["passed"]
            and target_mask_difference == 0
            and depth_order
            and clearance_passed
            and offset_passed
        )
        rows.append(
            {
                "frame_index": index,
                "timestamp_s": float(partial_info["timestamp"]),
                **relation,
                "target_projection_mask_difference_pixels": target_mask_difference,
                "partial_target_center_depth_m": partial_target_depth,
                "partial_occluder_center_depth_m": partial_occluder_depth,
                "strong_target_center_depth_m": strong_target_depth,
                "strong_occluder_center_depth_m": strong_occluder_depth,
                "partial_actor_clearance_m": partial_clearance,
                "strong_actor_clearance_m": strong_clearance,
                "partial_planar_offset_residual_m": partial_offset_residual,
                "strong_planar_offset_residual_m": strong_offset_residual,
                "planar_offset_passed": offset_passed,
                "depth_order_passed": depth_order,
                "clearance_passed": clearance_passed,
                "passed": passed,
            }
        )
    return {
        "frame_count": frame_count,
        "passed_frame_count": sum(row["passed"] for row in rows),
        "violation_count": sum(not row["passed"] for row in rows),
        "minimum_partial_coverage_fraction": min(
            row["partial_coverage_fraction"] for row in rows
        ),
        "median_partial_coverage_fraction": float(
            np.median([row["partial_coverage_fraction"] for row in rows])
        ),
        "maximum_partial_coverage_fraction": max(
            row["partial_coverage_fraction"] for row in rows
        ),
        "minimum_strong_coverage_fraction": min(
            row["strong_coverage_fraction"] for row in rows
        ),
        "median_strong_coverage_fraction": float(
            np.median([row["strong_coverage_fraction"] for row in rows])
        ),
        "maximum_strong_coverage_fraction": max(
            row["strong_coverage_fraction"] for row in rows
        ),
        "maximum_partial_outside_strong_pixels": max(
            row["partial_outside_strong_pixels"] for row in rows
        ),
        "maximum_partial_outside_strong_target_fraction": max(
            row["partial_outside_strong_target_fraction"] for row in rows
        ),
        "minimum_actor_clearance_m": min(
            min(row["partial_actor_clearance_m"], row["strong_actor_clearance_m"])
            for row in rows
        ),
        "maximum_planar_offset_residual_m": max(
            max(
                row["partial_planar_offset_residual_m"],
                row["strong_planar_offset_residual_m"],
            )
            for row in rows
        ),
        "passed": all(row["passed"] for row in rows),
        "frames": rows,
    }


def rgb_change_mask(left: np.ndarray, right: np.ndarray, threshold: int) -> np.ndarray:
    difference = np.max(
        np.abs(left.astype(np.int16) - right.astype(np.int16)), axis=2
    )
    return difference > threshold


def evaluate_support_masks(
    reference_mask: np.ndarray,
    partial_mask: np.ndarray,
    strong_mask: np.ndarray,
    minimum_baseline_pixels: int,
) -> dict[str, Any]:
    baseline_pixels = int(np.count_nonzero(reference_mask))
    if baseline_pixels < minimum_baseline_pixels:
        return {
            "outcome": "unavailable",
            "reason": "insufficient_unoccluded_target_support",
            "baseline_target_pixels": baseline_pixels,
            "partial_supported_pixels": None,
            "strong_supported_pixels": None,
            "partial_support_fraction": None,
            "strong_support_fraction": None,
        }
    partial_pixels = int(np.count_nonzero(reference_mask & partial_mask))
    strong_pixels = int(np.count_nonzero(reference_mask & strong_mask))
    partial_fraction = partial_pixels / baseline_pixels
    strong_fraction = strong_pixels / baseline_pixels
    return {
        "outcome": "expected" if partial_fraction >= strong_fraction else "reversal",
        "reason": None,
        "baseline_target_pixels": baseline_pixels,
        "partial_supported_pixels": partial_pixels,
        "strong_supported_pixels": strong_pixels,
        "partial_support_fraction": partial_fraction,
        "strong_support_fraction": strong_fraction,
    }


def background_changed_fraction(
    left: np.ndarray,
    right: np.ndarray,
    threshold: int,
    height_fraction: float,
) -> float:
    band_height = max(1, int(round(left.shape[0] * height_fraction)))
    return float(np.mean(rgb_change_mask(left[:band_height], right[:band_height], threshold)))


def support_metrics(
    observations: dict[str, list[dict[str, Any]]],
    infos: dict[str, list[dict[str, Any]]],
    camera: str,
    minimum_depth_m: float,
    threshold: int,
    minimum_baseline_pixels: int,
    background_height_fraction: float,
    maximum_background_changed_fraction: float,
) -> dict[str, Any]:
    frame_count = len(observations["no_actor"])
    if any(len(observations[condition]) != frame_count for condition in CONDITIONS):
        raise ValueError("observation counts differ")
    rows = []
    for index in range(frame_count):
        images = {
            condition: observations[condition][index]["rgb"][camera]
            for condition in CONDITIONS
        }
        image_shape = images["no_actor"].shape[:2]
        target = actor_box(
            infos["target_only"][index], ROLE_INDEX["target_only"]["target"]
        )
        target_mask, _ = projected_mask(
            infos["target_only"][index],
            target,
            camera,
            image_shape,
            minimum_depth_m,
        )
        partial_occluder = actor_box(
            infos["partial_both"][index], ROLE_INDEX["partial_both"]["occluder"]
        )
        strong_occluder = actor_box(
            infos["strong_both"][index], ROLE_INDEX["strong_both"]["occluder"]
        )
        partial_occluder_mask, _ = projected_mask(
            infos["partial_both"][index],
            partial_occluder,
            camera,
            image_shape,
            minimum_depth_m,
        )
        strong_occluder_mask, _ = projected_mask(
            infos["strong_both"][index],
            strong_occluder,
            camera,
            image_shape,
            minimum_depth_m,
        )
        nested_comparison_domain, partial_only_mask = nested_support_domain(
            target_mask, partial_occluder_mask, strong_occluder_mask
        )
        reference_change = (
            rgb_change_mask(images["target_only"], images["no_actor"], threshold)
            & nested_comparison_domain
        )
        partial_change = rgb_change_mask(
            images["partial_both"], images["partial_occluder_only"], threshold
        ) & nested_comparison_domain
        strong_change = rgb_change_mask(
            images["strong_both"], images["strong_occluder_only"], threshold
        ) & nested_comparison_domain
        background_fractions = {
            "target_only_vs_no_actor": background_changed_fraction(
                images["target_only"],
                images["no_actor"],
                threshold,
                background_height_fraction,
            ),
            "partial_both_vs_partial_occluder_only": background_changed_fraction(
                images["partial_both"],
                images["partial_occluder_only"],
                threshold,
                background_height_fraction,
            ),
            "strong_both_vs_strong_occluder_only": background_changed_fraction(
                images["strong_both"],
                images["strong_occluder_only"],
                threshold,
                background_height_fraction,
            ),
        }
        support = evaluate_support_masks(
            reference_change,
            partial_change,
            strong_change,
            minimum_baseline_pixels,
        )
        maximum_background = max(background_fractions.values())
        if maximum_background > maximum_background_changed_fraction:
            support = {
                **support,
                "excluded_partial_only_projected_pixels": int(
                    np.count_nonzero(partial_only_mask)
                ),
                "outcome": "unavailable",
                "reason": "paired_background_rendering_unstable",
            }
        rows.append(
            {
                "frame_index": index,
                "timestamp_s": float(infos["target_only"][index]["timestamp"]),
                **support,
                "background_changed_fractions": background_fractions,
                "maximum_background_changed_fraction": maximum_background,
            }
        )

    available = [row for row in rows if row["outcome"] != "unavailable"]
    reversal_count = sum(row["outcome"] == "reversal" for row in rows)
    unavailable_count = sum(row["outcome"] == "unavailable" for row in rows)
    partial_median = (
        float(np.median([row["partial_support_fraction"] for row in available]))
        if available
        else None
    )
    strong_median = (
        float(np.median([row["strong_support_fraction"] for row in available]))
        if available
        else None
    )
    strict_median_drop = bool(
        available and partial_median is not None and strong_median is not None
        and partial_median > strong_median
    )
    if reversal_count:
        evidence_label = "rejected"
    elif not available:
        evidence_label = "down-weighted"
    elif not strict_median_drop:
        evidence_label = "rejected"
    elif unavailable_count:
        evidence_label = "down-weighted"
    else:
        evidence_label = "accepted"
    return {
        "frame_count": frame_count,
        "available_count": len(available),
        "expected_count": sum(row["outcome"] == "expected" for row in rows),
        "reversal_count": reversal_count,
        "unavailable_count": unavailable_count,
        "median_partial_support_fraction": partial_median,
        "median_strong_support_fraction": strong_median,
        "strict_median_drop": strict_median_drop,
        "maximum_background_changed_fraction": max(
            row["maximum_background_changed_fraction"] for row in rows
        ),
        "evidence_label": evidence_label,
        "passed": evidence_label == "accepted",
        "frames": rows,
    }


def make_summary_figure(
    output: Path, geometry: dict[str, Any], support: dict[str, Any]
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    geometry_rows = geometry["frames"]
    support_rows = support["frames"]
    times = [row["timestamp_s"] for row in geometry_rows]
    axes[0, 0].plot(
        times,
        [row["partial_coverage_fraction"] for row in geometry_rows],
        label="Partial projected coverage",
        linewidth=2,
    )
    axes[0, 0].plot(
        times,
        [row["strong_coverage_fraction"] for row in geometry_rows],
        label="Strong projected coverage",
        linewidth=2,
    )
    axes[0, 0].set_title("Target-box overlap proxy")
    axes[0, 0].set_ylabel("Coverage fraction")

    axes[0, 1].plot(
        [row["timestamp_s"] for row in support_rows],
        [np.nan if row["partial_support_fraction"] is None else row["partial_support_fraction"] for row in support_rows],
        label="Partial target support",
        linewidth=2,
    )
    axes[0, 1].plot(
        [row["timestamp_s"] for row in support_rows],
        [np.nan if row["strong_support_fraction"] is None else row["strong_support_fraction"] for row in support_rows],
        label="Strong target support",
        linewidth=2,
    )
    axes[0, 1].set_title("Factorially isolated target RGB support")
    axes[0, 1].set_ylabel("Support fraction")

    axes[1, 0].plot(
        [row["timestamp_s"] for row in support_rows],
        [row["baseline_target_pixels"] for row in support_rows],
        color="#2b6cb0",
        linewidth=2,
    )
    axes[1, 0].set_title("Unoccluded target reference support")
    axes[1, 0].set_ylabel("Changed pixels")

    axes[1, 1].plot(
        [row["timestamp_s"] for row in support_rows],
        [row["maximum_background_changed_fraction"] for row in support_rows],
        color="#805ad5",
        linewidth=2,
    )
    axes[1, 1].set_title("Paired background control-band drift")
    axes[1, 1].set_ylabel("Changed-pixel fraction")
    for axis in axes.flat:
        axis.set_xlabel("Simulation time (s)")
        axis.grid(alpha=0.25)
        axis.legend() if axis.lines and len(axis.lines) > 1 else None
    figure.suptitle("HUGSIM CF-O 001: controlled occlusion indicators", fontsize=16)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def make_contact_sheet(
    output: Path,
    observations: dict[str, list[dict[str, Any]]],
    infos: dict[str, list[dict[str, Any]]],
    camera: str,
) -> None:
    frame_count = len(observations["target_only"])
    indices = (0, frame_count // 2, frame_count - 1)
    display_conditions = ("target_only", "partial_both", "strong_both")
    figure, axes = plt.subplots(3, 3, figsize=(16, 9), constrained_layout=True)
    for row_index, frame_index in enumerate(indices):
        for column_index, condition in enumerate(display_conditions):
            axes[row_index, column_index].imshow(
                observations[condition][frame_index]["rgb"][camera]
            )
            axes[row_index, column_index].set_title(
                f"{DISPLAY_NAMES[condition]}  t={float(infos[condition][frame_index]['timestamp']):.2f}s"
            )
            axes[row_index, column_index].set_xticks([])
            axes[row_index, column_index].set_yticks([])
    figure.suptitle("Raw HUGSIM CAM_FRONT inputs for CF-O 001", fontsize=16)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def make_comparison_video(
    output: Path,
    observations: dict[str, list[dict[str, Any]]],
    support: dict[str, Any],
    camera: str,
) -> None:
    display_conditions = ("target_only", "partial_both", "strong_both")
    tile_width, tile_height = 640, 360
    writer = cv2.VideoWriter(
        str(output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        4.0,
        (tile_width * len(display_conditions), tile_height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"could not open video writer: {output}")
    try:
        for index, support_row in enumerate(support["frames"]):
            canvas = np.zeros(
                (tile_height, tile_width * len(display_conditions), 3), dtype=np.uint8
            )
            for column, condition in enumerate(display_conditions):
                image = observations[condition][index]["rgb"][camera]
                tile = cv2.resize(
                    image, (tile_width, tile_height), interpolation=cv2.INTER_AREA
                )
                if condition == "partial_both":
                    value = support_row["partial_support_fraction"]
                elif condition == "strong_both":
                    value = support_row["strong_support_fraction"]
                else:
                    value = 1.0
                support_text = "NA" if value is None else f"{value:.3f}"
                label = (
                    f"{DISPLAY_NAMES[condition]}  t={support_row['timestamp_s']:.2f}s  "
                    f"support={support_text}"
                )
                cv2.putText(tile, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(tile, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (255, 255, 255), 2, cv2.LINE_AA)
                start = column * tile_width
                canvas[:, start : start + tile_width] = tile
            writer.write(cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    preregistration = load_json(preregistration_path)
    if preregistration["audit_id"] != "hugsim_occlusion_metamorphic_001":
        raise ValueError("unexpected preregistration audit ID")
    if sha256_file(Path(__file__).resolve()) != preregistration["analysis_script_sha256"]:
        raise ValueError("current analysis script differs from preregistration")
    preregistration_commit = verify_preregistration_commit(
        repo_root, args.preregistration_commit, preregistration_path, preregistration
    )
    controller_source = Path(preregistration["controller_source"]["path"])
    if sha256_file(controller_source) != preregistration["controller_source"]["sha256"]:
        raise ValueError("ConstantPlanner source hash differs from preregistration")

    run_paths = {}
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        config = (repo_root / spec["config"]).resolve()
        if sha256_file(config) != spec["config_sha256"]:
            raise ValueError(f"{condition}: config hash differs from preregistration")
        run_paths[condition] = (repo_root / spec["output"]).resolve()

    audits = {condition: load_json(path / "audit_summary.json") for condition, path in run_paths.items()}
    writer_summaries = {condition: load_json(path / "plan_writer_summary.json") for condition, path in run_paths.items()}
    infos = {condition: load_pickle(path / "infos.pkl") for condition, path in run_paths.items()}
    steps = {condition: load_pickle(path / "audit_steps.pkl") for condition, path in run_paths.items()}
    observations = {condition: load_pickle(path / "observations.pkl") for condition, path in run_paths.items()}

    fixed = preregistration["fixed_design"]
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        audit = audits[condition]
        source_assets = audit["source_assets"]
        if source_assets["scenario_yaml_sha256"] != spec["config_sha256"]:
            raise ValueError(f"{condition}: run used a non-preregistered scenario")
        expected_config = (repo_root / spec["config"]).resolve()
        if Path(source_assets["scenario_yaml"]).resolve() != expected_config:
            raise ValueError(f"{condition}: run scenario path differs")
        if audit["requested_steps"] != fixed["max_steps"] or audit["completed_steps"] != fixed["max_steps"]:
            raise ValueError(f"{condition}: run did not complete the preregistered step count")
        if audit["audit_repo"]["commit"] != preregistration_commit:
            raise ValueError(f"{condition}: run audit commit differs")
        if audit["audit_repo"]["worktree_status"]:
            raise ValueError(f"{condition}: run started from a dirty audit worktree")
        writer = writer_summaries[condition]
        writer_checks = {
            "status": writer["status"] == "complete",
            "horizon": writer["horizon"] == fixed["plan_writer_horizon"],
            "step_m": writer["step_m"] == fixed["plan_writer_step_m"],
            "max_steps": writer["max_steps"] == fixed["max_steps"],
            "responses_sent": writer["responses_sent"] == fixed["max_steps"],
            "done_received": writer["done_received"] is True,
            "audit_repo_commit": writer["audit_repo_commit"] == preregistration_commit,
        }
        failed_writer_checks = [name for name, passed in writer_checks.items() if not passed]
        if failed_writer_checks:
            raise ValueError(f"{condition}: plan writer contract differs: " + ", ".join(failed_writer_checks))

    pairing = {}
    for condition in CONDITIONS[1:]:
        pairing[condition] = {
            "input_validation": validate_run_pairing(
                audits["no_actor"], audits[condition], infos["no_actor"], infos[condition], steps["no_actor"], steps[condition]
            ),
            "ego_action_differences": paired_differences(
                infos["no_actor"], infos[condition], steps["no_actor"], steps[condition]
            ),
        }
        if any(pairing[condition]["ego_action_differences"].values()):
            raise ValueError(f"{condition}: ego/action trajectory differs")

    role_checks = role_invariance(
        infos, float(preregistration["numeric_tolerances"]["actor_state_max_abs"])
    )
    actor_state_tolerance = float(
        preregistration["numeric_tolerances"]["actor_state_max_abs"]
    )
    camera = fixed["camera"]
    image_shape = observations["no_actor"][0]["rgb"][camera].shape[:2]
    projection_spec = preregistration["projection"]
    geometry = geometry_metrics(
        infos,
        image_shape,
        camera,
        float(projection_spec["minimum_center_depth_m"]),
        float(projection_spec["minimum_actor_clearance_m"]),
        float(projection_spec["maximum_partial_outside_strong_target_fraction"]),
        float(fixed["target_forward_m"] - fixed["occluder_forward_m"]),
        float(fixed["partial_occluder_right_m"] - fixed["target_right_m"]),
        float(fixed["strong_occluder_right_m"] - fixed["target_right_m"]),
        actor_state_tolerance,
    )
    rgb_spec = preregistration["rgb_support"]
    support = support_metrics(
        observations,
        infos,
        camera,
        float(projection_spec["minimum_center_depth_m"]),
        int(rgb_spec["difference_threshold"]),
        int(rgb_spec["minimum_baseline_pixels"]),
        float(rgb_spec["background_control_height_fraction"]),
        float(rgb_spec["maximum_background_changed_fraction"]),
    )
    geometry_passed = role_checks["passed"] and geometry["passed"]
    geometry_label = "accepted" if geometry_passed else "rejected"
    support_label = support["evidence_label"]
    if support_label == "accepted" and not geometry_passed:
        support_label = "down-weighted"
    if geometry_label == "rejected" or support_label == "rejected":
        overall_label = "rejected"
    else:
        overall_label = "down-weighted"

    summary = {
        "audit_id": preregistration["audit_id"],
        "preregistration_commit": preregistration_commit,
        "run_paths": {condition: str(path) for condition, path in run_paths.items()},
        "scope": preregistration["scope"],
        "pairing": pairing,
        "role_state_invariance": role_checks,
        "geometry": geometry,
        "rgb_target_support": support,
        "claims": {
            "controlled_occlusion_geometry": geometry_label,
            "target_rgb_support_monotonicity": support_label,
        },
        "overall_segment_evidence_label": overall_label,
        "independence_notice": preregistration["independence_notice"],
        "strongest_allowed_claim": preregistration["strongest_allowed_claim"],
        "forbidden_claims": preregistration["forbidden_claims"],
    }
    (output / "occlusion_metamorphic_audit.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    make_summary_figure(output / "occlusion_indicator_summary.png", geometry, support)
    make_contact_sheet(output / "occlusion_cam_front_contact_sheet.png", observations, infos, camera)
    make_comparison_video(output / "occlusion_cam_front_comparison.mp4", observations, support, camera)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
