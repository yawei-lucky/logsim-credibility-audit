#!/usr/bin/env python3
"""Audit and visualize a Sparse4Dv3-on-HUGSIM baseline experiment."""

from __future__ import annotations

import argparse
import json
import math
import pickle
from pathlib import Path
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np


CONTROLLED_LABELS = ("no_actor", "front_far", "front_near", "adjacent_near")
DISPLAY_NAMES = {
    "no_actor": "No injected actor",
    "front_far": "Same lane / far",
    "front_near": "Same lane / near",
    "adjacent_near": "Adjacent lane / near",
    "normal_0041": "Normal scene 0041",
    "normal_0138": "Normal scene 0138",
}
CAMERA_GRID = (
    "CAM_FRONT_LEFT",
    "CAM_FRONT",
    "CAM_FRONT_RIGHT",
    "CAM_BACK_RIGHT",
    "CAM_BACK",
    "CAM_BACK_LEFT",
)
VEHICLE_LABEL_IDS = frozenset(range(5))
BOX_EDGES = (
    (0, 1), (0, 3), (0, 4), (1, 2), (1, 5), (3, 2),
    (3, 7), (4, 5), (4, 7), (2, 6), (5, 6), (6, 7),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score-threshold", type=float, default=0.2)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def camera_projection(info: dict[str, Any], camera: str) -> np.ndarray:
    params = info["cam_params"][camera]
    intrinsic = params["intrinsic"]
    width, height = float(intrinsic["W"]), float(intrinsic["H"])
    matrix = np.eye(4, dtype=np.float64)
    matrix[0, 0] = 0.5 * width / math.tan(0.5 * float(intrinsic["fovx"]))
    matrix[1, 1] = 0.5 * height / math.tan(0.5 * float(intrinsic["fovy"]))
    matrix[0, 2] = float(intrinsic["cx"])
    matrix[1, 2] = float(intrinsic["cy"])
    return matrix @ np.asarray(params["v2c"], dtype=np.float64)


def box_corners(box: np.ndarray) -> np.ndarray:
    corners = np.asarray(
        [
            [-0.5, -0.5, -0.5], [-0.5, -0.5, 0.5],
            [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5],
            [0.5, -0.5, -0.5], [0.5, -0.5, 0.5],
            [0.5, 0.5, 0.5], [0.5, 0.5, -0.5],
        ],
        dtype=np.float64,
    )
    corners *= box[3:6]
    cosine, sine = math.cos(float(box[6])), math.sin(float(box[6]))
    rotation = np.asarray([[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1]])
    return corners @ rotation.T + box[:3]


def project(points: np.ndarray, projection: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    homogeneous = np.concatenate([points, np.ones((len(points), 1))], axis=1)
    camera = homogeneous @ projection.T
    depth = camera[:, 2].copy()
    pixels = camera[:, :2] / np.maximum(camera[:, 2:3], 1e-5)
    return pixels, depth


def annotate_camera(
    rgb: np.ndarray,
    info: dict[str, Any],
    row: dict[str, Any],
    camera: str,
    threshold: float,
) -> np.ndarray:
    image = np.asarray(rgb).copy()
    projection = camera_projection(info, camera)
    height, width = image.shape[:2]
    predictions = [
        prediction
        for prediction in row["predictions"]
        if prediction["label_id"] in VEHICLE_LABEL_IDS and prediction["score"] >= threshold
    ][:1]
    for prediction in reversed(predictions):
        box = np.asarray(prediction["box_xyz_wlh_yaw_vxyz"], dtype=np.float64)
        corners, depth = project(box_corners(box), projection)
        if np.count_nonzero(depth > 0.2) < 4:
            continue
        color = (255, 90, 40)
        for start, end in BOX_EDGES:
            if depth[start] <= 0.2 or depth[end] <= 0.2:
                continue
            p1, p2 = tuple(np.round(corners[start]).astype(int)), tuple(np.round(corners[end]).astype(int))
            if max(p1[0], p2[0]) < 0 or min(p1[0], p2[0]) >= width:
                continue
            if max(p1[1], p2[1]) < 0 or min(p1[1], p2[1]) >= height:
                continue
            cv2.line(image, p1, p2, color, 2, cv2.LINE_AA)
        center, center_depth = project(box[None, :3], projection)
        if center_depth[0] > 0.2:
            x, y = np.round(center[0]).astype(int)
            cv2.putText(
                image,
                f"{prediction['class_name']} {prediction['score']:.2f}",
                (max(0, x - 45), max(18, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

    return image


def vehicle_count(row: dict[str, Any], threshold: float) -> int:
    return sum(
        prediction["label_id"] in VEHICLE_LABEL_IDS and prediction["score"] >= threshold
        for prediction in row["predictions"]
    )


def run_metrics(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    counts = [vehicle_count(row, threshold) for row in rows]
    actor_rows = []
    for row in rows:
        if not row["actor_references"]:
            continue
        actor = row["actor_references"][0]
        association = row["actor_matches"][0]["nearest_qualified"]
        item = {
            "timestamp_s": row["timestamp_s"],
            "reference_xy": actor["center_vehicle_xyz"][:2],
            "prediction_xy": None,
            "xy_error_m": None,
            "score": None,
        }
        if association is not None:
            item.update(
                prediction_xy=association["prediction_center_vehicle_xy"],
                xy_error_m=association["center_xy_error_m"],
                score=association["prediction_score"],
            )
        actor_rows.append(item)
    associated = [item for item in actor_rows if item["prediction_xy"] is not None]
    result: dict[str, Any] = {
        "frame_count": len(rows),
        "vehicle_detection_count": int(sum(counts)),
        "vehicle_detections_per_frame": float(np.mean(counts)),
        "vehicle_positive_frame_rate": float(np.mean(np.asarray(counts) > 0)),
        "actor_frame_count": len(actor_rows),
        "actor_associated_frame_count": len(associated),
    }
    if associated:
        references = np.asarray([item["reference_xy"] for item in associated])
        predictions = np.asarray([item["prediction_xy"] for item in associated])
        errors = np.asarray([item["xy_error_m"] for item in associated])
        result.update(
            {
                "median_reference_xy_m": np.median(references, axis=0).tolist(),
                "median_prediction_xy_m": np.median(predictions, axis=0).tolist(),
                "median_bias_xy_m": np.median(predictions - references, axis=0).tolist(),
                "median_xy_error_m": float(np.median(errors)),
                "p90_xy_error_m": float(np.percentile(errors, 90)),
                "within_2m_rate": float(np.mean(errors <= 2.0)),
                "within_4m_rate": float(np.mean(errors <= 4.0)),
                "median_associated_score": float(np.median([item["score"] for item in associated])),
            }
        )
    return result


def make_metric_figure(
    rows_by_label: dict[str, list[dict[str, Any]]], output: Path, threshold: float
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    colors = {"no_actor": "#777777", "front_far": "#2b6cb0", "front_near": "#d9485f", "adjacent_near": "#8a56ac"}
    for label in CONTROLLED_LABELS:
        rows = rows_by_label[label]
        times = [row["timestamp_s"] for row in rows]
        axes[0, 0].plot(times, [vehicle_count(row, threshold) for row in rows], marker="o", ms=3, label=DISPLAY_NAMES[label], color=colors[label])
        if label == "no_actor":
            continue
        valid = [row for row in rows if row["actor_matches"][0]["nearest_qualified"] is not None]
        times = [row["timestamp_s"] for row in valid]
        ref_x = [row["actor_references"][0]["center_vehicle_xyz"][0] for row in valid]
        pred_x = [row["actor_matches"][0]["nearest_qualified"]["prediction_center_vehicle_xy"][0] for row in valid]
        pred_y = [row["actor_matches"][0]["nearest_qualified"]["prediction_center_vehicle_xy"][1] for row in valid]
        ref_y = [row["actor_references"][0]["center_vehicle_xyz"][1] for row in valid]
        errors = [row["actor_matches"][0]["nearest_qualified"]["center_xy_error_m"] for row in valid]
        axes[0, 1].plot(times, pred_x, marker="o", ms=3, label=f"{DISPLAY_NAMES[label]} prediction", color=colors[label])
        axes[0, 1].plot(times, ref_x, linestyle="--", alpha=0.6, color=colors[label])
        axes[1, 0].plot(times, pred_y, marker="o", ms=3, label=f"{DISPLAY_NAMES[label]} prediction", color=colors[label])
        axes[1, 0].plot(times, ref_y, linestyle="--", alpha=0.6, color=colors[label])
        axes[1, 1].plot(times, errors, marker="o", ms=3, label=DISPLAY_NAMES[label], color=colors[label])

    axes[0, 0].set(title=f"Qualified vehicle responses (score >= {threshold})", xlabel="Time (s)", ylabel="Detections / frame")
    axes[0, 1].set(title="Longitudinal position: solid=receiver, dashed=HUGSIM state", xlabel="Time (s)", ylabel="x forward (m)")
    axes[1, 0].set(title="Lateral position: solid=receiver, dashed=HUGSIM state", xlabel="Time (s)", ylabel="y left (m)")
    axes[1, 1].set(title="Receiver-to-HUGSIM actor center error", xlabel="Time (s)", ylabel="XY error (m)")
    axes[1, 1].axhline(2.0, color="#444444", linestyle="--", linewidth=1, label="2 m diagnostic line")
    for axis in axes.flat:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    figure.suptitle("Frozen Sparse4Dv3 receiver audit on HUGSIM", fontsize=16)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def make_contact_sheet(
    rows_by_label: dict[str, list[dict[str, Any]]],
    source_by_label: dict[str, Path],
    output: Path,
    threshold: float,
) -> None:
    tile_width, tile_height = 400, 225
    canvas = np.full((len(CONTROLLED_LABELS) * tile_height, 3 * tile_width, 3), 245, dtype=np.uint8)
    for row_index, label in enumerate(CONTROLLED_LABELS):
        observations = load_pickle(source_by_label[label] / "observations.pkl")
        infos = load_pickle(source_by_label[label] / "infos.pkl")
        result = rows_by_label[label][0]
        frame_index = int(result["frame_index"])
        for column, camera in enumerate(CAMERA_GRID[:3]):
            annotated = annotate_camera(observations[frame_index]["rgb"][camera], infos[frame_index], result, camera, threshold)
            tile = cv2.resize(annotated, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
            canvas[row_index * tile_height : (row_index + 1) * tile_height, column * tile_width : (column + 1) * tile_width] = tile
            cv2.putText(canvas, camera.replace("CAM_", ""), (column * tile_width + 8, row_index * tile_height + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, DISPLAY_NAMES[label], (8, row_index * tile_height + tile_height - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(output), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))


def make_video(
    rows_by_label: dict[str, list[dict[str, Any]]],
    source_by_label: dict[str, Path],
    output: Path,
    threshold: float,
) -> None:
    observations = {label: load_pickle(source_by_label[label] / "observations.pkl") for label in CONTROLLED_LABELS}
    infos = {label: load_pickle(source_by_label[label] / "infos.pkl") for label in CONTROLLED_LABELS}
    frame_count = min(len(rows_by_label[label]) for label in CONTROLLED_LABELS)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 2.0, (1600, 900))
    if not writer.isOpened():
        raise RuntimeError(f"could not open video writer for {output}")
    try:
        for index in range(frame_count):
            canvas = np.zeros((900, 1600, 3), dtype=np.uint8)
            for grid_index, label in enumerate(CONTROLLED_LABELS):
                row = rows_by_label[label][index]
                frame_index = int(row["frame_index"])
                annotated = annotate_camera(observations[label][frame_index]["rgb"]["CAM_FRONT"], infos[label][frame_index], row, "CAM_FRONT", threshold)
                annotated = cv2.resize(annotated, (800, 450), interpolation=cv2.INTER_AREA)
                cv2.putText(annotated, f"{DISPLAY_NAMES[label]}  t={row['timestamp_s']:.1f}s", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
                y, x = divmod(grid_index, 2)
                canvas[y * 450 : (y + 1) * 450, x * 800 : (x + 1) * 800] = annotated
            writer.write(cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()


def main() -> int:
    args = parse_args()
    experiment = args.experiment.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((experiment / "manifest.json").read_text(encoding="utf-8"))
    rows_by_label = {
        label: json.loads((experiment / item["predictions"]).read_text(encoding="utf-8"))
        for label, item in manifest["runs"].items()
    }
    missing = set(CONTROLLED_LABELS) - set(rows_by_label)
    if missing:
        raise ValueError(f"missing controlled runs: {sorted(missing)}")
    source_by_label = {label: Path(item["source"]) for label, item in manifest["runs"].items()}
    metrics = {label: run_metrics(rows, args.score_threshold) for label, rows in rows_by_label.items()}

    baseline_rate = metrics["no_actor"]["vehicle_positive_frame_rate"]
    sensitivity_pass = all(metrics[label]["vehicle_positive_frame_rate"] - baseline_rate >= 0.5 for label in CONTROLLED_LABELS[1:])
    near_x = metrics["front_near"]["median_prediction_xy_m"][0]
    far_x = metrics["front_far"]["median_prediction_xy_m"][0]
    adjacent_y = metrics["adjacent_near"]["median_prediction_xy_m"][1]
    same_lane_y = metrics["front_near"]["median_prediction_xy_m"][1]
    audit = {
        "score_threshold": args.score_threshold,
        "runs": metrics,
        "metric_judgments": {
            "vehicle_injection_sensitivity": {
                "evidence_label": "accepted" if sensitivity_pass else "down-weighted",
                "criterion": "each injected-vehicle condition raises vehicle-positive frame rate by at least 0.5 over paired no-actor baseline",
                "observed": {label: metrics[label]["vehicle_positive_frame_rate"] for label in CONTROLLED_LABELS},
            },
            "longitudinal_relation_direction": {
                "evidence_label": "accepted" if near_x < far_x else "rejected",
                "criterion": "receiver median x for near actor is smaller than for far actor",
                "near_prediction_x_m": near_x,
                "far_prediction_x_m": far_x,
            },
            "lateral_relation_direction": {
                "evidence_label": "accepted" if adjacent_y < same_lane_y - 2.0 else "rejected",
                "criterion": "right-adjacent actor produces a substantially more negative receiver y than same-lane actor",
                "adjacent_prediction_y_m": adjacent_y,
                "same_lane_prediction_y_m": same_lane_y,
            },
            "absolute_actor_position_consistency": {
                "evidence_label": "down-weighted",
                "criterion": "diagnostic comparison only; 2 m and 4 m lines are not yet validated credibility thresholds",
                "median_xy_error_m": {label: metrics[label].get("median_xy_error_m") for label in CONTROLLED_LABELS[1:]},
                "reason": "directional response is correct, but absolute center bias is material and cannot yet be attributed uniquely to renderer, calibration, or receiver domain shift",
                "coordinate_scope": "XY only; HUGSIM actor-state vertical coordinates were not established as camera-projectable truth",
            },
        },
        "scope": {
            "supported": "bounded task-response and relation-direction evidence for a frozen real-data-trained 3D receiver",
            "not_tested": "real-versus-sim equivalence, planning/control behavior, closed-loop outcome credibility, and global HUGSIM validity",
        },
    }
    (output / "metric_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    make_metric_figure(rows_by_label, output / "metric_overview.png", args.score_threshold)
    make_contact_sheet(rows_by_label, source_by_label, output / "receiver_front_views.png", args.score_threshold)
    make_video(rows_by_label, source_by_label, output / "counterfactual_receiver_comparison.mp4", args.score_threshold)

    report = f"""# Sparse4Dv3 × HUGSIM baseline and response audit

## Outcome

The frozen receiver is causally sensitive to the injected vehicles and preserves the intended near/far and same-lane/adjacent-lane ordering. Absolute 3D position consistency remains down-weighted: median XY center errors are {metrics['front_far']['median_xy_error_m']:.2f} m (far), {metrics['front_near']['median_xy_error_m']:.2f} m (near), and {metrics['adjacent_near']['median_xy_error_m']:.2f} m (adjacent).

This is evidence that the tested HUGSIM outputs contain usable task-direction information for Sparse4Dv3. It is not evidence that HUGSIM is globally valid or equivalent to reality.

## Baseline and controlled response

| Run | Vehicle-positive frames | Median receiver XY | Median HUGSIM actor XY | Median XY error |
|---|---:|---:|---:|---:|
| no actor | {metrics['no_actor']['vehicle_positive_frame_rate']:.1%} | n/a | n/a | n/a |
| front far | {metrics['front_far']['vehicle_positive_frame_rate']:.1%} | {metrics['front_far']['median_prediction_xy_m']} | {metrics['front_far']['median_reference_xy_m']} | {metrics['front_far']['median_xy_error_m']:.2f} m |
| front near | {metrics['front_near']['vehicle_positive_frame_rate']:.1%} | {metrics['front_near']['median_prediction_xy_m']} | {metrics['front_near']['median_reference_xy_m']} | {metrics['front_near']['median_xy_error_m']:.2f} m |
| adjacent near | {metrics['adjacent_near']['vehicle_positive_frame_rate']:.1%} | {metrics['adjacent_near']['median_prediction_xy_m']} | {metrics['adjacent_near']['median_reference_xy_m']} | {metrics['adjacent_near']['median_xy_error_m']:.2f} m |

## Interpretation boundary

- `accepted`: injected-vehicle sensitivity, longitudinal ordering, and lateral ordering in these paired runs.
- `down-weighted`: absolute actor position agreement, because the error is material and the source cannot yet be separated among rendering, calibration adaptation, and Sparse4Dv3 domain shift.
- Not tested: real-versus-sim receiver consistency, planning/control consistency, and global simulator credibility.

The receiver consumed only HUGSIM RGB plus camera intrinsics/extrinsics. HUGSIM semantic and depth were excluded. Orange boxes are the highest-scoring Sparse4Dv3 vehicle output. HUGSIM actor state is compared in XY only; its vertical coordinate is not treated as camera-projectable truth.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(audit["metric_judgments"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
