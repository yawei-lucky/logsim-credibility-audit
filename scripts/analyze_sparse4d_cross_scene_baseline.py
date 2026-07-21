#!/usr/bin/env python3
"""Aggregate normal-scene and controlled Sparse4Dv3 HUGSIM evidence."""

from __future__ import annotations

import argparse
import json
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np

from analyze_sparse4d_hugsim_baseline import CAMERA_GRID, DISPLAY_NAMES, annotate_camera


NORMAL_LABELS = ("no_actor", "normal_0041", "normal_0138")
CONTROLLED_LABELS = ("front_far", "front_near", "adjacent_near")
ALL_LABEL_IDS = frozenset(range(10))
VEHICLE_LABEL_IDS = frozenset(range(5))
THRESHOLDS = (0.2, 0.3, 0.5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def qualified(row: dict[str, Any], threshold: float, labels: frozenset[int]) -> list[dict[str, Any]]:
    return [
        prediction
        for prediction in row["predictions"]
        if prediction["score"] >= threshold and prediction["label_id"] in labels
    ]


def summarize_normal_scene(rows: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for threshold in THRESHOLDS:
        all_predictions = [prediction for row in rows for prediction in qualified(row, threshold, ALL_LABEL_IDS)]
        vehicle_predictions = [prediction for prediction in all_predictions if prediction["label_id"] in VEHICLE_LABEL_IDS]
        thresholds[str(threshold)] = {
            "all_detection_count": len(all_predictions),
            "all_positive_frame_count": sum(bool(qualified(row, threshold, ALL_LABEL_IDS)) for row in rows),
            "all_positive_frame_rate": float(np.mean([bool(qualified(row, threshold, ALL_LABEL_IDS)) for row in rows])),
            "vehicle_detection_count": len(vehicle_predictions),
            "vehicle_positive_frame_count": sum(bool(qualified(row, threshold, VEHICLE_LABEL_IDS)) for row in rows),
            "vehicle_positive_frame_rate": float(np.mean([bool(qualified(row, threshold, VEHICLE_LABEL_IDS)) for row in rows])),
            "class_counts": dict(sorted(Counter(prediction["class_name"] for prediction in all_predictions).items())),
        }

    tracks: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for prediction in qualified(row, 0.2, ALL_LABEL_IDS):
            tracks[(int(prediction.get("instance_id", -1)), prediction["class_name"])].append(
                {"timestamp_s": row["timestamp_s"], "score": prediction["score"]}
            )
    track_rows = []
    for (instance_id, class_name), observations in tracks.items():
        track_rows.append(
            {
                "instance_id": instance_id,
                "class_name": class_name,
                "frame_count": len(observations),
                "first_timestamp_s": observations[0]["timestamp_s"],
                "last_timestamp_s": observations[-1]["timestamp_s"],
                "maximum_score": max(item["score"] for item in observations),
            }
        )
    track_rows.sort(key=lambda item: (item["frame_count"], item["maximum_score"]), reverse=True)
    return {
        "frame_count": len(rows),
        "thresholds": thresholds,
        "track_count_at_0.2": len(track_rows),
        "longest_tracks_at_0.2": track_rows[:10],
    }


def lane_relation(y: float) -> str:
    if abs(y) <= 2.0:
        return "same_lane"
    return "left_adjacent_or_beyond" if y > 2.0 else "right_adjacent_or_beyond"


def controlled_operational_metrics(rows_by_label: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    lane_rows = []
    continuity: dict[str, Any] = {}
    metric_bias: dict[str, Any] = {}
    for label in CONTROLLED_LABELS:
        associated = []
        ids = []
        references = []
        predictions = []
        for row in rows_by_label[label]:
            if not row["actor_references"]:
                continue
            association = row["actor_matches"][0]["nearest_qualified"]
            reference_y = float(row["actor_references"][0]["center_vehicle_xyz"][1])
            if association is None:
                lane_rows.append(
                    {
                        "run_label": label,
                        "timestamp_s": row["timestamp_s"],
                        "reference_relation": lane_relation(reference_y),
                        "prediction_relation": "not_detected",
                        "agreement": False,
                    }
                )
                continue
            prediction_y = float(association["prediction_center_vehicle_xy"][1])
            prediction = row["predictions"][association["prediction_rank"]]
            ids.append(int(prediction.get("instance_id", -1)))
            associated.append(row)
            references.append(row["actor_references"][0]["center_vehicle_xyz"][:2])
            predictions.append(association["prediction_center_vehicle_xy"])
            lane_rows.append(
                {
                    "run_label": label,
                    "timestamp_s": row["timestamp_s"],
                    "reference_relation": lane_relation(reference_y),
                    "prediction_relation": lane_relation(prediction_y),
                    "agreement": lane_relation(reference_y) == lane_relation(prediction_y),
                }
            )
        id_counts = Counter(ids)
        continuity[label] = {
            "frame_count": len(rows_by_label[label]),
            "associated_frame_count": len(associated),
            "association_rate": len(associated) / len(rows_by_label[label]),
            "unique_associated_instance_ids": sorted(id_counts),
            "dominant_instance_fraction_of_associated": (
                max(id_counts.values()) / len(ids) if ids else None
            ),
        }
        reference_array = np.asarray(references, dtype=np.float64)
        prediction_array = np.asarray(predictions, dtype=np.float64)
        bias = np.median(prediction_array - reference_array, axis=0)
        reference_median = np.median(reference_array, axis=0)
        metric_bias[label] = {
            "median_reference_xy_m": reference_median.tolist(),
            "median_prediction_xy_m": np.median(prediction_array, axis=0).tolist(),
            "median_bias_xy_m": bias.tolist(),
            "median_xy_error_m": float(
                np.median(np.linalg.norm(prediction_array - reference_array, axis=1))
            ),
            "longitudinal_bias_fraction_of_median_reference_x": (
                float(abs(bias[0]) / abs(reference_median[0]))
                if abs(reference_median[0]) > 2.0
                else None
            ),
            "lateral_bias_fraction_of_reference_lane_offset": (
                float(abs(bias[1]) / abs(reference_median[1]))
                if abs(reference_median[1]) > 1e-6
                else None
            ),
        }

    near_by_time = {row["timestamp_s"]: row for row in rows_by_label["front_near"]}
    far_by_time = {row["timestamp_s"]: row for row in rows_by_label["front_far"]}
    ordering = []
    for timestamp in sorted(set(near_by_time) & set(far_by_time)):
        near = near_by_time[timestamp]
        far = far_by_time[timestamp]
        near_match = near["actor_matches"][0]["nearest_qualified"]
        far_match = far["actor_matches"][0]["nearest_qualified"]
        if near_match is None or far_match is None:
            continue
        near_x = float(near_match["prediction_center_vehicle_xy"][0])
        far_x = float(far_match["prediction_center_vehicle_xy"][0])
        ordering.append(
            {
                "timestamp_s": timestamp,
                "near_prediction_x_m": near_x,
                "far_prediction_x_m": far_x,
                "correct": near_x < far_x,
            }
        )
    return {
        "lane_relation": {
            "definition": "same lane when |y| <= 2 m; 2 m is the midpoint between the designed y=0 and y=-4 m intervention centers, not a general lane-width threshold",
            "evaluated_frame_count": len(lane_rows),
            "agreement_count": sum(row["agreement"] for row in lane_rows),
            "agreement_rate": float(np.mean([row["agreement"] for row in lane_rows])),
            "rows": lane_rows,
        },
        "near_far_ordering": {
            "evaluated_pair_count": len(ordering),
            "correct_pair_count": sum(row["correct"] for row in ordering),
            "agreement_rate": float(np.mean([row["correct"] for row in ordering])),
            "rows": ordering,
        },
        "track_continuity": continuity,
        "metric_bias": metric_bias,
    }


def make_summary_figure(summary: dict[str, Any], output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    colors = {"no_actor": "#6b7280", "normal_0041": "#2b6cb0", "normal_0138": "#d9485f"}
    x = np.arange(len(THRESHOLDS))
    width = 0.24
    for index, label in enumerate(NORMAL_LABELS):
        scene = summary["normal_scenes"][label]
        axes[0, 0].bar(
            x + (index - 1) * width,
            [scene["thresholds"][str(threshold)]["vehicle_positive_frame_rate"] for threshold in THRESHOLDS],
            width,
            label=DISPLAY_NAMES[label],
            color=colors[label],
        )
        axes[0, 1].bar(
            x + (index - 1) * width,
            [scene["thresholds"][str(threshold)]["all_positive_frame_rate"] for threshold in THRESHOLDS],
            width,
            label=DISPLAY_NAMES[label],
            color=colors[label],
        )
    for axis, title in (
        (axes[0, 0], "Vehicle-positive frame rate vs score threshold"),
        (axes[0, 1], "Any-class positive frame rate vs score threshold"),
    ):
        axis.set_xticks(x, [str(threshold) for threshold in THRESHOLDS])
        axis.set(xlabel="Sparse4Dv3 score threshold", ylabel="Positive frame rate", title=title, ylim=(0, 1.05))
        axis.grid(axis="y", alpha=0.25)
        axis.legend(fontsize=8)

    classes = sorted(
        {
            class_name
            for label in NORMAL_LABELS
            for class_name in summary["normal_scenes"][label]["thresholds"]["0.2"]["class_counts"]
        }
    )
    bottom = np.zeros(len(NORMAL_LABELS))
    palette = plt.cm.Set2(np.linspace(0, 1, max(1, len(classes))))
    for class_name, color in zip(classes, palette, strict=True):
        values = [summary["normal_scenes"][label]["thresholds"]["0.2"]["class_counts"].get(class_name, 0) for label in NORMAL_LABELS]
        axes[1, 0].bar([DISPLAY_NAMES[label] for label in NORMAL_LABELS], values, bottom=bottom, label=class_name, color=color)
        bottom += np.asarray(values)
    axes[1, 0].set(title="Class counts at score >= 0.2", ylabel="Detections across 19 frames")
    axes[1, 0].tick_params(axis="x", rotation=10)
    axes[1, 0].legend(fontsize=8)
    axes[1, 0].grid(axis="y", alpha=0.25)

    operational = summary["controlled_operational_endpoints"]
    values = [
        operational["near_far_ordering"]["agreement_rate"],
        operational["lane_relation"]["agreement_rate"],
        operational["track_continuity"]["front_far"]["dominant_instance_fraction_of_associated"],
        operational["track_continuity"]["front_near"]["dominant_instance_fraction_of_associated"],
        operational["track_continuity"]["adjacent_near"]["dominant_instance_fraction_of_associated"],
    ]
    endpoint_names = ["Near<far\nordering", "Lane relation", "Far track", "Near track", "Adjacent track"]
    bars = axes[1, 1].bar(endpoint_names, values, color=["#2b6cb0", "#8a56ac", "#4c9f70", "#4c9f70", "#4c9f70"])
    axes[1, 1].bar_label(bars, labels=[f"{value:.0%}" for value in values], padding=3)
    axes[1, 1].set(title="Controlled task-relative endpoints", ylabel="Agreement / dominant-track fraction", ylim=(0, 1.1))
    axes[1, 1].grid(axis="y", alpha=0.25)
    figure.suptitle("Sparse4Dv3 cross-scene HUGSIM receiver evidence", fontsize=16)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def make_contact_sheet(
    label: str,
    rows: list[dict[str, Any]],
    source: Path,
    output: Path,
) -> None:
    observations = load_pickle(source / "observations.pkl")
    infos = load_pickle(source / "infos.pkl")
    selected = [0, len(rows) // 2, len(rows) - 1]
    tile_width, tile_height = 400, 225
    canvas = np.zeros((3 * tile_height, 6 * tile_width, 3), dtype=np.uint8)
    for row_index, selected_index in enumerate(selected):
        row = rows[selected_index]
        frame_index = int(row["frame_index"])
        for column, camera in enumerate(CAMERA_GRID):
            annotated = annotate_camera(
                observations[frame_index]["rgb"][camera],
                infos[frame_index],
                row,
                camera,
                0.2,
                label_ids=ALL_LABEL_IDS,
                max_predictions=8,
            )
            tile = cv2.resize(annotated, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
            y0, x0 = row_index * tile_height, column * tile_width
            canvas[y0 : y0 + tile_height, x0 : x0 + tile_width] = tile
            cv2.putText(canvas, camera.replace("CAM_", ""), (x0 + 8, y0 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"{DISPLAY_NAMES[label]} t={row['timestamp_s']:.1f}s", (8, row_index * tile_height + tile_height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(output), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))


def make_six_camera_video(
    label: str,
    rows: list[dict[str, Any]],
    source: Path,
    output: Path,
) -> None:
    observations = load_pickle(source / "observations.pkl")
    infos = load_pickle(source / "infos.pkl")
    widths = (533, 533, 534)
    tile_height = 450
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 2.0, (1600, 900))
    if not writer.isOpened():
        raise RuntimeError(f"could not open {output}")
    try:
        for row in rows:
            canvas = np.zeros((900, 1600, 3), dtype=np.uint8)
            frame_index = int(row["frame_index"])
            for camera_index, camera in enumerate(CAMERA_GRID):
                annotated = annotate_camera(
                    observations[frame_index]["rgb"][camera],
                    infos[frame_index],
                    row,
                    camera,
                    0.2,
                    label_ids=ALL_LABEL_IDS,
                    max_predictions=8,
                )
                grid_y, grid_x = divmod(camera_index, 3)
                width = widths[grid_x]
                tile = cv2.resize(annotated, (width, tile_height), interpolation=cv2.INTER_AREA)
                x0 = sum(widths[:grid_x])
                y0 = grid_y * tile_height
                canvas[y0 : y0 + tile_height, x0 : x0 + width] = tile
                cv2.putText(canvas, camera.replace("CAM_", ""), (x0 + 10, y0 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(canvas, f"{DISPLAY_NAMES[label]}  t={row['timestamp_s']:.1f}s", (15, 885), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)
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
    required = set(NORMAL_LABELS) | set(CONTROLLED_LABELS)
    if missing := required - set(rows_by_label):
        raise ValueError(f"missing runs: {sorted(missing)}")
    sources = {label: Path(item["source"]) for label, item in manifest["runs"].items()}

    summary = {
        "normal_scenes": {
            label: summarize_normal_scene(rows_by_label[label]) for label in NORMAL_LABELS
        },
        "controlled_operational_endpoints": controlled_operational_metrics(rows_by_label),
        "evidence_judgments": {
            "controlled_detection_and_relation_endpoints": {
                "evidence_label": "accepted",
                "supported_use": "coarse object presence, near/far ordering, lane relation, and short temporal identity continuity in the tested counterfactuals",
            },
            "absolute_3d_localization_for_planning": {
                "evidence_label": "down-weighted",
                "reason": "material XY bias remains; task-specific planning/control invariance has not been tested",
            },
            "normal_scene_semantic_correctness": {
                "evidence_label": "down-weighted",
                "reason": "response and persistence are measured, but native objects and nuisance regions lack independent labels",
            },
        },
        "layer_position": {
            "current_primary": "task-level receiver consistency candidate",
            "not_yet_sensor_consistency": "no matched real sensor observation or independent sensor reference is available",
            "supporting_contract_only": "six-camera array, preprocessing, calibration-format, and temporal input contracts",
        },
    }
    (output / "cross_scene_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    make_summary_figure(summary, output / "cross_scene_summary.png")
    for label in NORMAL_LABELS:
        make_contact_sheet(label, rows_by_label[label], sources[label], output / f"{label}_receiver_contact_sheet.png")
    for label in ("normal_0041", "normal_0138"):
        make_six_camera_video(label, rows_by_label[label], sources[label], output / f"{label}_six_camera_receiver.mp4")

    normal = summary["normal_scenes"]
    operational = summary["controlled_operational_endpoints"]
    report = f"""# Sparse4Dv3 cross-scene baseline and operational endpoint summary

## Result

The current experiment is primarily a **task-level receiver-consistency candidate**, not sensor-consistency evidence. Sparse4Dv3 receives the simulated sensor arrays, but no matched real sensor observation or independent sensor reference is available.

## Normal-scene baseline

| Scene | Vehicle-positive frames @0.2 | @0.3 | @0.5 | Main qualified classes @0.2 |
|---|---:|---:|---:|---|
| scene-0383 no injected actor | {normal['no_actor']['thresholds']['0.2']['vehicle_positive_frame_count']}/19 | {normal['no_actor']['thresholds']['0.3']['vehicle_positive_frame_count']}/19 | {normal['no_actor']['thresholds']['0.5']['vehicle_positive_frame_count']}/19 | {normal['no_actor']['thresholds']['0.2']['class_counts']} |
| scene-0041 | {normal['normal_0041']['thresholds']['0.2']['vehicle_positive_frame_count']}/19 | {normal['normal_0041']['thresholds']['0.3']['vehicle_positive_frame_count']}/19 | {normal['normal_0041']['thresholds']['0.5']['vehicle_positive_frame_count']}/19 | {normal['normal_0041']['thresholds']['0.2']['class_counts']} |
| scene-0138 | {normal['normal_0138']['thresholds']['0.2']['vehicle_positive_frame_count']}/19 | {normal['normal_0138']['thresholds']['0.3']['vehicle_positive_frame_count']}/19 | {normal['normal_0138']['thresholds']['0.5']['vehicle_positive_frame_count']}/19 | {normal['normal_0138']['thresholds']['0.2']['class_counts']} |

`scene-0041` vehicle response is weak and collapses as the score threshold rises. `scene-0138` contains persistent pedestrian responses and weaker bus/car responses around roadside and bus-stop structures. These are useful nuisance/coverage observations, but not precision or recall without independent labels.

## AD-task-relative endpoints

- near/far longitudinal ordering: {operational['near_far_ordering']['correct_pair_count']}/{operational['near_far_ordering']['evaluated_pair_count']} aligned pairs;
- same/adjacent lane relation: {operational['lane_relation']['agreement_count']}/{operational['lane_relation']['evaluated_frame_count']} actor frames;
- far actor dominant track fraction: {operational['track_continuity']['front_far']['dominant_instance_fraction_of_associated']:.1%};
- near actor dominant track fraction: {operational['track_continuity']['front_near']['dominant_instance_fraction_of_associated']:.1%};
- adjacent actor dominant track fraction: {operational['track_continuity']['adjacent_near']['dominant_instance_fraction_of_associated']:.1%}.

Absolute geometry remains materially weaker: the near condition has an {operational['metric_bias']['front_near']['longitudinal_bias_fraction_of_median_reference_x']:.1%} longitudinal bias relative to its median configured range, while the adjacent condition has a {operational['metric_bias']['adjacent_near']['lateral_bias_fraction_of_reference_lane_offset']:.1%} lateral bias relative to the designed 4 m lane offset. These ratios are diagnostics, not universal acceptance thresholds.

This is enough for bounded **presence, relation, ordering, and short-track** use. It is not enough to support metric 3D localization for planning, collision prediction, or closed-loop outcome evaluation. Whether the remaining range error is acceptable must be decided by downstream decision invariance: does the same AD planner preserve its risk order and action under matched real and simulated inputs?

## Evidence boundary

- `accepted`: controlled object sensitivity, relation direction, ordering, and temporal identity endpoints in the tested conditions;
- `down-weighted`: absolute localization for planning and normal-scene semantic correctness;
- not tested: matched real-sim sensor consistency, planner/control invariance, and closed-loop credibility.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary["evidence_judgments"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
