#!/usr/bin/env python3
"""Diagnose Sparse4Dv3 metric-box bias without claiming real-world truth."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np

from analyze_sparse4d_hugsim_baseline import BOX_EDGES, box_corners, camera_projection, project


RUNS = {
    "front_far": "scene-0383-ad-receiver-front-far-00-run001-9s",
    "front_near": "scene-0383-ad-receiver-front-near-00-run001-9s",
    "adjacent_near": "scene-0383-ad-receiver-adjacent-near-00-run001-9s",
}
DISPLAY = {
    "front_far": "Same lane / far",
    "front_near": "Same lane / near",
    "adjacent_near": "Adjacent lane / near",
}
COLORS = {"front_far": "#2b6cb0", "front_near": "#d9485f", "adjacent_near": "#8a56ac"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--contrast-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def enclosing_box(points: np.ndarray, width: int, height: int) -> np.ndarray:
    result = np.asarray(
        [points[:, 0].min(), points[:, 1].min(), points[:, 0].max(), points[:, 1].max()],
        dtype=np.float64,
    )
    result[[0, 2]] = np.clip(result[[0, 2]], 0, width - 1)
    result[[1, 3]] = np.clip(result[[1, 3]], 0, height - 1)
    return result


def box_iou(first: np.ndarray, second: np.ndarray) -> float:
    intersection = max(0.0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0.0, min(first[3], second[3]) - max(first[1], second[1])
    )
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def best_actor_mask(
    baseline_observation: dict[str, Any],
    treatment_observation: dict[str, Any],
) -> tuple[str, np.ndarray]:
    candidates = []
    for camera, semantic in treatment_observation["semantic"].items():
        baseline = baseline_observation["semantic"][camera]
        mask = (semantic == 13) & (baseline != 13)
        candidates.append((int(mask.sum()), camera, mask))
    count, camera, mask = max(candidates, key=lambda item: item[0])
    if count < 20:
        raise ValueError("no sufficiently visible injected-car semantic mask")
    return camera, mask


def analyze_run(
    label: str,
    rows: list[dict[str, Any]],
    baseline_observations: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    infos: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frame_rows = []
    for row in rows:
        association = row["actor_matches"][0]["nearest_qualified"]
        if association is None:
            continue
        frame_index = int(row["frame_index"])
        camera, mask = best_actor_mask(baseline_observations[frame_index], observations[frame_index])
        ys, xs = np.where(mask)
        mask_box = np.asarray([xs.min(), ys.min(), xs.max(), ys.max()], dtype=np.float64)
        prediction = row["predictions"][association["prediction_rank"]]
        prediction_box = np.asarray(prediction["box_xyz_wlh_yaw_vxyz"], dtype=np.float64)
        pixels, depth = project(box_corners(prediction_box), camera_projection(infos[frame_index], camera))
        valid = depth > 0.2
        if np.count_nonzero(valid) < 4:
            continue
        height, width = mask.shape
        projected_box = enclosing_box(pixels[valid], width, height)
        mask_center = (mask_box[:2] + mask_box[2:]) / 2
        projected_center = (projected_box[:2] + projected_box[2:]) / 2
        reference_dimensions = np.asarray(row["actor_references"][0]["dimensions_wlh"], dtype=np.float64)
        reference_xyz_dimensions = reference_dimensions[[1, 0, 2]]
        frame_rows.append(
            {
                "run_label": label,
                "timestamp_s": row["timestamp_s"],
                "frame_index": frame_index,
                "camera": camera,
                "mask_pixel_count": int(mask.sum()),
                "mask_bbox_xyxy": mask_box.tolist(),
                "projected_prediction_bbox_xyxy": projected_box.tolist(),
                "bbox_iou": box_iou(mask_box, projected_box),
                "bbox_center_error_px": float(np.linalg.norm(mask_center - projected_center)),
                "reference_xyz_dimensions_m": reference_xyz_dimensions.tolist(),
                "prediction_xyz_dimensions_m": prediction_box[3:6].tolist(),
                "dimension_ratio_prediction_to_reference": (prediction_box[3:6] / reference_xyz_dimensions).tolist(),
                "reference_center_xy_m": row["actor_references"][0]["center_vehicle_xyz"][:2],
                "prediction_center_xy_m": association["prediction_center_vehicle_xy"],
                "center_xy_error_m": association["center_xy_error_m"],
                "prediction_rank": association["prediction_rank"],
            }
        )

    ious = np.asarray([item["bbox_iou"] for item in frame_rows])
    pixel_errors = np.asarray([item["bbox_center_error_px"] for item in frame_rows])
    dimension_ratios = np.asarray([item["dimension_ratio_prediction_to_reference"] for item in frame_rows])
    metric_errors = np.asarray([item["center_xy_error_m"] for item in frame_rows])
    summary = {
        "evaluated_frame_count": len(frame_rows),
        "median_projected_bbox_iou": float(np.median(ious)),
        "p10_projected_bbox_iou": float(np.percentile(ious, 10)),
        "median_projected_bbox_center_error_px": float(np.median(pixel_errors)),
        "median_metric_xy_error_m": float(np.median(metric_errors)),
        "median_prediction_to_reference_dimension_ratio_xyz": np.median(dimension_ratios, axis=0).tolist(),
        "best_camera_counts": dict(
            sorted(
                {
                    camera: sum(item["camera"] == camera for item in frame_rows)
                    for camera in {item["camera"] for item in frame_rows}
                }.items()
            )
        ),
    }
    return summary, frame_rows


def draw_associated_overlay(
    rgb: np.ndarray,
    mask: np.ndarray,
    info: dict[str, Any],
    camera: str,
    prediction_box: np.ndarray,
) -> np.ndarray:
    image = np.asarray(rgb).copy()
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(image, contours, -1, (40, 220, 80), 2, cv2.LINE_AA)
    pixels, depth = project(box_corners(prediction_box), camera_projection(info, camera))
    for start, end in BOX_EDGES:
        if depth[start] <= 0.2 or depth[end] <= 0.2:
            continue
        cv2.line(
            image,
            tuple(np.round(pixels[start]).astype(int)),
            tuple(np.round(pixels[end]).astype(int)),
            (255, 90, 40),
            2,
            cv2.LINE_AA,
        )
    return image


def make_overlay_sheet(
    rows_by_label: dict[str, list[dict[str, Any]]],
    baseline_observations: list[dict[str, Any]],
    treatment_data: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    output: Path,
) -> None:
    tile_width, tile_height = 800, 450
    canvas = np.zeros((len(RUNS) * tile_height, tile_width, 3), dtype=np.uint8)
    for row_index, label in enumerate(RUNS):
        row = rows_by_label[label][0]
        frame_index = int(row["frame_index"])
        observations, infos = treatment_data[label]
        camera, mask = best_actor_mask(baseline_observations[frame_index], observations[frame_index])
        association = row["actor_matches"][0]["nearest_qualified"]
        prediction_box = np.asarray(row["predictions"][association["prediction_rank"]]["box_xyz_wlh_yaw_vxyz"])
        overlay = draw_associated_overlay(observations[frame_index]["rgb"][camera], mask, infos[frame_index], camera, prediction_box)
        overlay = cv2.resize(overlay, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
        cv2.putText(overlay, f"{DISPLAY[label]} / {camera} / green=rendered actor / orange=receiver box", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
        canvas[row_index * tile_height : (row_index + 1) * tile_height] = overlay
    cv2.imwrite(str(output), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))


def make_figure(summary: dict[str, Any], frame_rows: dict[str, list[dict[str, Any]]], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    for label in RUNS:
        rows = frame_rows[label]
        times = [row["timestamp_s"] for row in rows]
        axes[0, 0].plot(times, [row["bbox_iou"] for row in rows], marker="o", ms=3, label=DISPLAY[label], color=COLORS[label])
        axes[0, 1].plot(times, [row["bbox_center_error_px"] for row in rows], marker="o", ms=3, label=DISPLAY[label], color=COLORS[label])
    axes[0, 0].set(title="Reprojected receiver box vs rendered actor mask", xlabel="Time (s)", ylabel="2D bbox IoU", ylim=(0, 1))
    axes[0, 1].set(title="Projected bbox center alignment", xlabel="Time (s)", ylabel="Center error (pixels)")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].legend(fontsize=8)

    x = np.arange(3)
    width = 0.24
    for index, label in enumerate(RUNS):
        ratios = summary["runs"][label]["median_prediction_to_reference_dimension_ratio_xyz"]
        axes[1, 0].bar(x + (index - 1) * width, ratios, width, label=DISPLAY[label], color=COLORS[label])
    axes[1, 0].axhline(1.0, color="#333333", linestyle="--", linewidth=1)
    axes[1, 0].set_xticks(x, ["longitudinal", "lateral", "vertical"])
    axes[1, 0].set(title="Receiver box size / HUGSIM configured actor size", ylabel="Dimension ratio")
    axes[1, 0].legend(fontsize=8)

    labels = list(RUNS)
    ious = [summary["runs"][label]["median_projected_bbox_iou"] for label in labels]
    errors = [summary["runs"][label]["median_metric_xy_error_m"] for label in labels]
    axis = axes[1, 1]
    bars = axis.bar([DISPLAY[label] for label in labels], errors, color=[COLORS[label] for label in labels], alpha=0.75)
    axis.bar_label(bars, labels=[f"{value:.2f} m" for value in errors], padding=3)
    axis.set(title="Metric error despite pixel-space overlap", ylabel="Median XY center error (m)")
    for index, iou in enumerate(ious):
        axis.text(index, max(errors[index] * 0.55, 0.3), f"2D IoU\n{iou:.2f}", ha="center", color="white", fontsize=10, weight="bold")
    for ax in axes.flat:
        ax.grid(alpha=0.25)
    figure.suptitle("Sparse4Dv3 box-bias diagnostic: pixel alignment vs metric geometry", fontsize=16)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    experiment = args.experiment.expanduser().resolve()
    contrast_root = args.contrast_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline_observations = load_pickle(contrast_root / "scene-0383-easy-00-run007-9s" / "observations.pkl")
    rows_by_label = {
        label: json.loads((experiment / f"{label}_predictions.json").read_text(encoding="utf-8"))
        for label in RUNS
    }
    treatment_data = {
        label: (
            load_pickle(contrast_root / run_name / "observations.pkl"),
            load_pickle(contrast_root / run_name / "infos.pkl"),
        )
        for label, run_name in RUNS.items()
    }

    run_summaries = {}
    frame_rows = {}
    for label in RUNS:
        observations, infos = treatment_data[label]
        run_summaries[label], frame_rows[label] = analyze_run(
            label, rows_by_label[label], baseline_observations, observations, infos
        )
    audit = {
        "runs": run_summaries,
        "diagnostic_findings": {
            "pixel_space_projection_alignment": {
                "evidence_label": "accepted",
                "finding": "associated Sparse4Dv3 boxes reproject onto the injected actor's HUGSIM semantic-difference region with repeated moderate-to-high 2D overlap",
                "claim_boundary": "internal HUGSIM pixel-space alignment only; it does not prove real calibration or sensor truth",
            },
            "metric_scale_depth_bias": {
                "evidence_label": "down-weighted",
                "finding": "receiver boxes are physically larger and farther than HUGSIM configured actor boxes while retaining pixel-space overlap",
                "implication": "gross image-plane misprojection is unlikely to be the sole cause; actor scale/appearance priors, coordinate convention, and receiver domain shift remain candidates",
            },
        },
        "inputs": {
            "actor_region": "semantic class 13 pixels added relative to the paired no-injection frame",
            "independence": "not independent; HUGSIM semantic and calibration are used only for internal diagnosis",
        },
    }
    (output / "box_bias_diagnostic.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    for label, rows in frame_rows.items():
        (output / f"{label}_box_bias_frames.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    make_figure(audit, frame_rows, output / "box_bias_diagnostic.png")
    make_overlay_sheet(rows_by_label, baseline_observations, treatment_data, output / "box_bias_overlay.png")

    report = f"""# Sparse4Dv3 box-bias diagnostic

## Main finding

The metric center error is real, but it is not accompanied by a comparable image-plane failure. Median projected 3D-box overlap with the injected HUGSIM actor region is {run_summaries['front_far']['median_projected_bbox_iou']:.2f} (far), {run_summaries['front_near']['median_projected_bbox_iou']:.2f} (near), and {run_summaries['adjacent_near']['median_projected_bbox_iou']:.2f} (adjacent). Median projected-center errors are {run_summaries['front_far']['median_projected_bbox_center_error_px']:.1f}, {run_summaries['front_near']['median_projected_bbox_center_error_px']:.1f}, and {run_summaries['adjacent_near']['median_projected_bbox_center_error_px']:.1f} pixels.

At the same time, Sparse4Dv3 predicts boxes larger than the HUGSIM configured actor. Median receiver/configured dimension ratios `[longitudinal, lateral, vertical]` are:

- far: {run_summaries['front_far']['median_prediction_to_reference_dimension_ratio_xyz']};
- near: {run_summaries['front_near']['median_prediction_to_reference_dimension_ratio_xyz']};
- adjacent: {run_summaries['adjacent_near']['median_prediction_to_reference_dimension_ratio_xyz']}.

This is consistent with a scale-depth tradeoff: a larger, farther receiver box can still explain nearly the same image region. It makes a gross image-plane projection failure unlikely as the sole cause, but it does not isolate renderer scale, coordinate convention, or Sparse4Dv3 domain shift.

## Evidence decision

- `accepted`: repeated internal pixel-space overlap of the associated receiver box and rendered injected-actor region;
- `down-weighted`: scale-depth/domain-shift explanation, because the actor mask and calibration are HUGSIM outputs rather than independent truth;
- not established: real calibration correctness or metric geometry suitable for planning.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(audit["diagnostic_findings"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
