#!/usr/bin/env python3
"""Create and audit a fixed human-visible normal-scene Sparse4D sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np

from analyze_sparse4d_hugsim_baseline import (
    BOX_EDGES,
    box_corners,
    camera_projection,
    project,
)


SCENES = ("normal_0041", "normal_0138")
SCORE_THRESHOLD = 0.2
ALLOWED_LABELS = frozenset(
    {"supported_target", "class_mismatch", "nuisance", "uncertain"}
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def fixed_sample_positions(frame_count: int) -> list[int]:
    if frame_count < 3:
        raise ValueError("at least three receiver frames are required")
    return [0, frame_count // 2, frame_count - 1]


def projection_candidate(
    box: np.ndarray,
    info: dict[str, Any],
    camera: str,
    image_shape: tuple[int, ...],
) -> dict[str, Any] | None:
    height, width = image_shape[:2]
    projection = camera_projection(info, camera)
    center_pixel, center_depth = project(box[None, :3], projection)
    if center_depth[0] <= 0.2:
        return None
    corners, depth = project(box_corners(box), projection)
    valid = depth > 0.2
    if np.count_nonzero(valid) < 4:
        return None
    raw = np.asarray(
        [
            corners[valid, 0].min(),
            corners[valid, 1].min(),
            corners[valid, 0].max(),
            corners[valid, 1].max(),
        ],
        dtype=np.float64,
    )
    clipped = raw.copy()
    clipped[[0, 2]] = np.clip(clipped[[0, 2]], 0, width - 1)
    clipped[[1, 3]] = np.clip(clipped[[1, 3]], 0, height - 1)
    area = max(0.0, clipped[2] - clipped[0]) * max(0.0, clipped[3] - clipped[1])
    cx, cy = center_pixel[0]
    center_in_extended_view = -0.25 * width <= cx <= 1.25 * width and -0.25 * height <= cy <= 1.25 * height
    if area < 16 or not center_in_extended_view:
        return None
    return {
        "camera": camera,
        "area_px": area,
        "bbox_xyxy": clipped.tolist(),
        "corner_pixels": corners.tolist(),
        "corner_depths": depth.tolist(),
    }


def camera_projection_candidates(
    box: np.ndarray,
    info: dict[str, Any],
    observation: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    for camera, rgb in observation["rgb"].items():
        candidate = projection_candidate(box, info, camera, rgb.shape)
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        raise ValueError("prediction does not project into any camera")
    return sorted(candidates, key=lambda item: item["area_px"], reverse=True)


def expanded_crop(bbox: list[float], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
    crop_width = max(180.0, (x2 - x1) * 2.2)
    crop_height = max(135.0, (y2 - y1) * 2.2)
    crop_width = min(crop_width, width)
    crop_height = min(crop_height, height)
    left = int(np.clip(center_x - crop_width / 2, 0, width - crop_width))
    top = int(np.clip(center_y - crop_height / 2, 0, height - crop_height))
    return [left, top, int(left + crop_width), int(top + crop_height)]


def build_manifest(experiment: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    receiver_manifest = json.loads((experiment / "manifest.json").read_text(encoding="utf-8"))
    records = []
    cache: dict[str, Any] = {}
    for scene in SCENES:
        run = receiver_manifest["runs"][scene]
        rows = json.loads((experiment / run["predictions"]).read_text(encoding="utf-8"))
        source = Path(run["source"])
        observations = load_pickle(source / "observations.pkl")
        infos = load_pickle(source / "infos.pkl")
        cache[scene] = {"rows": rows, "observations": observations, "infos": infos}
        for sample_position in fixed_sample_positions(len(rows)):
            row = rows[sample_position]
            frame_index = int(row["frame_index"])
            qualified = [
                prediction
                for prediction in row["predictions"]
                if prediction["score"] >= SCORE_THRESHOLD
            ]
            for prediction in qualified:
                box = np.asarray(prediction["box_xyz_wlh_yaw_vxyz"], dtype=np.float64)
                candidates = camera_projection_candidates(
                    box, infos[frame_index], observations[frame_index]
                )
                projection = candidates[0]
                camera = projection["camera"]
                rgb = observations[frame_index]["rgb"][camera]
                detection_id = f"{scene}_f{frame_index:03d}_r{prediction['rank']:03d}"
                records.append(
                    {
                        "detection_id": detection_id,
                        "scene": scene,
                        "sample_position": sample_position,
                        "frame_index": frame_index,
                        "timestamp_s": float(row["timestamp_s"]),
                        "prediction_rank": int(prediction["rank"]),
                        "instance_id": int(prediction.get("instance_id", -1)),
                        "class_name": prediction["class_name"],
                        "score": float(prediction["score"]),
                        "box_xyz_wlh_yaw_vxyz": prediction["box_xyz_wlh_yaw_vxyz"],
                        "best_camera": camera,
                        "projected_bbox_xyxy": projection["bbox_xyxy"],
                        "crop_xyxy": expanded_crop(projection["bbox_xyxy"], rgb.shape[1], rgb.shape[0]),
                        "projection_candidates": [
                            {
                                "camera": candidate["camera"],
                                "area_px": candidate["area_px"],
                                "bbox_xyxy": candidate["bbox_xyxy"],
                                "crop_xyxy": expanded_crop(
                                    candidate["bbox_xyxy"],
                                    observations[frame_index]["rgb"][candidate["camera"]].shape[1],
                                    observations[frame_index]["rgb"][candidate["camera"]].shape[0],
                                ),
                                "raw_rgb_sha256": array_sha256(
                                    observations[frame_index]["rgb"][candidate["camera"]]
                                ),
                            }
                            for candidate in candidates
                        ],
                        "raw_rgb_sha256": array_sha256(rgb),
                    }
                )
    manifest = {
        "selection_rule": {
            "scenes": list(SCENES),
            "receiver_frame_positions": "first, middle, last",
            "score_threshold": SCORE_THRESHOLD,
            "prediction_classes": "all Sparse4Dv3 classes",
            "camera_selection": "top two cameras by visible projected 3D-box area are shown for human review",
            "selection_frozen_before_human_labels": True,
        },
        "claim_boundary": (
            "human support within HUGSIM rendered RGB; not real-world correctness; "
            "detection-conditioned sample cannot estimate false negatives or recall"
        ),
        "record_count": len(records),
        "records": records,
    }
    return manifest, cache


def draw_prediction(rgb: np.ndarray, info: dict[str, Any], camera: str, box: np.ndarray) -> np.ndarray:
    image = np.asarray(rgb).copy()
    pixels, depths = project(box_corners(box), camera_projection(info, camera))
    for start, end in BOX_EDGES:
        if depths[start] <= 0.2 or depths[end] <= 0.2:
            continue
        cv2.line(
            image,
            tuple(np.round(pixels[start]).astype(int)),
            tuple(np.round(pixels[end]).astype(int)),
            (255, 95, 35),
            2,
            cv2.LINE_AA,
        )
    return image


def make_atlas(manifest: dict[str, Any], cache: dict[str, Any], output: Path) -> None:
    tile_width, tile_height = 640, 300
    columns = 3
    rows = math.ceil(len(manifest["records"]) / columns)
    canvas = np.full((rows * tile_height, columns * tile_width, 3), 20, dtype=np.uint8)
    for index, record in enumerate(manifest["records"]):
        scene_data = cache[record["scene"]]
        observation = scene_data["observations"][record["frame_index"]]
        info = scene_data["infos"][record["frame_index"]]
        available_height = tile_height - 54
        row_index, column_index = divmod(index, columns)
        view_width = tile_width // 2
        for view_index, candidate in enumerate(record["projection_candidates"][:2]):
            camera = candidate["camera"]
            image = draw_prediction(
                observation["rgb"][camera],
                info,
                camera,
                np.asarray(record["box_xyz_wlh_yaw_vxyz"], dtype=np.float64),
            )
            x1, y1, x2, y2 = candidate["crop_xyxy"]
            crop = image[y1:y2, x1:x2]
            scale = min(view_width / crop.shape[1], available_height / crop.shape[0])
            resized = cv2.resize(
                crop,
                (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
            base_x = column_index * tile_width + view_index * view_width
            x0 = base_x + (view_width - resized.shape[1]) // 2
            y0 = row_index * tile_height + 54 + (available_height - resized.shape[0]) // 2
            canvas[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
            cv2.putText(
                canvas,
                camera.replace("CAM_", ""),
                (base_x + 7, row_index * tile_height + tile_height - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (235, 235, 235),
                1,
                cv2.LINE_AA,
            )
        header_y = row_index * tile_height
        cv2.putText(canvas, record["detection_id"], (column_index * tile_width + 7, header_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 240), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"{record['class_name']} {record['score']:.3f} / top two projected views", (column_index * tile_width + 7, header_y + 43), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 170, 80), 1, cv2.LINE_AA)
    cv2.imwrite(str(output), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))


def load_annotations(path: Path, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    annotations = {item["detection_id"]: item for item in payload["annotations"]}
    if set(annotations) != expected_ids:
        raise ValueError("annotation IDs must exactly match the frozen manifest")
    for detection_id, item in annotations.items():
        if item.get("label") not in ALLOWED_LABELS:
            raise ValueError(f"{detection_id}: invalid label {item.get('label')}")
        if not item.get("region_type") or not item.get("notes"):
            raise ValueError(f"{detection_id}: region_type and notes are required")
    return annotations


def summarize(manifest: dict[str, Any], annotations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joined = []
    for record in manifest["records"]:
        joined.append({**record, **annotations[record["detection_id"]]})
    counts = Counter(item["label"] for item in joined)
    decidable = [item for item in joined if item["label"] != "uncertain"]
    result = {
        "record_count": len(joined),
        "label_counts": dict(sorted(counts.items())),
        "decidable_count": len(decidable),
        "supported_target_rate_all": counts["supported_target"] / len(joined),
        "supported_target_rate_decidable": counts["supported_target"] / len(decidable) if decidable else None,
        "nuisance_or_mismatch_rate_decidable": (
            (counts["nuisance"] + counts["class_mismatch"]) / len(decidable)
            if decidable
            else None
        ),
        "by_scene": {},
        "by_predicted_class": {},
        "region_type_counts": dict(sorted(Counter(item["region_type"] for item in joined).items())),
        "records": joined,
        "evidence_judgments": {
            "fixed_annotation_protocol": {
                "evidence_label": "accepted",
                "claim": "the sample is deterministic, complete for the declared rule, and linked to hashed receiver RGB",
            },
            "normal_scene_receiver_semantic_support": {
                "evidence_label": "down-weighted",
                "claim": "small-sample human-visible support within HUGSIM RGB only",
                "limitation": (
                    "not real-world truth, not exhaustive frames, detection-conditioned, "
                    "and not a receiver precision or recall estimate for the ODD"
                ),
            },
        },
    }
    for field, values in (
        ("by_scene", SCENES),
        ("by_predicted_class", sorted({item["class_name"] for item in joined})),
    ):
        key = "scene" if field == "by_scene" else "class_name"
        for value in values:
            subset = [item for item in joined if item[key] == value]
            result[field][value] = {
                "count": len(subset),
                "label_counts": dict(sorted(Counter(item["label"] for item in subset).items())),
            }
    return result


def make_summary_figure(summary: dict[str, Any], output: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    labels = ["supported_target", "class_mismatch", "nuisance", "uncertain"]
    colors = ["#3a9464", "#d68c32", "#c94c4c", "#777777"]
    scene_names = list(SCENES)
    bottom = np.zeros(len(scene_names))
    for label, color in zip(labels, colors, strict=True):
        values = [summary["by_scene"][scene]["label_counts"].get(label, 0) for scene in scene_names]
        axes[0].bar(scene_names, values, bottom=bottom, label=label, color=color)
        bottom += np.asarray(values)
    axes[0].set(title="Human-visible support by normal scene", ylabel="Sampled Sparse4Dv3 predictions")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.25)

    regions = summary["region_type_counts"]
    axes[1].barh(list(regions), list(regions.values()), color="#657fa8")
    axes[1].set(title="Visible target / nuisance region types", xlabel="Sampled predictions")
    axes[1].grid(axis="x", alpha=0.25)
    figure.suptitle("Fixed normal-scene Sparse4Dv3 annotation audit", fontsize=15)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    experiment = args.experiment.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest, cache = build_manifest(experiment)
    (output / "annotation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    make_atlas(manifest, cache, output / "annotation_atlas.png")
    if args.annotations is None:
        print(json.dumps({"record_count": manifest["record_count"], "status": "awaiting_annotations"}, indent=2))
        return 0

    annotations = load_annotations(
        args.annotations.expanduser().resolve(),
        {record["detection_id"] for record in manifest["records"]},
    )
    summary = summarize(manifest, annotations)
    (output / "labelled_nuisance_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    make_summary_figure(summary, output / "labelled_nuisance_summary.png")
    print(json.dumps({key: summary[key] for key in ("record_count", "label_counts", "supported_target_rate_decidable", "nuisance_or_mismatch_rate_decidable")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
