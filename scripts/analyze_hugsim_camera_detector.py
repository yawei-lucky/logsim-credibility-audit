#!/usr/bin/env python3
"""Analyze HUGSIM counterfactuals with a frozen camera-only detector.

This receiver uses a COCO-pretrained torchvision detector on CAM_FRONT RGB.
It is closer to an AD perception receiver than the semantic/depth proxy, but
it is still not a full AD stack and must not be reported as planning/control
or closed-loop AD behavior.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torchvision.transforms.functional import to_tensor


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-hugsim-camera-detector")
os.environ.setdefault(
    "TORCH_HOME",
    "/home/yawei/logsim-credibility-audit/artifacts/model_cache/torch",
)

ROAD_CLASSES = ("bicycle", "car", "motorcycle", "bus", "truck")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a frozen camera-only detector on HUGSIM RGB outputs."
    )
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run spec in the form label=/path/to/run.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--camera", default="CAM_FRONT")
    parser.add_argument("--score-threshold", type=float, default=0.25)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
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


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_run_specs(specs: list[str]) -> dict[str, Path]:
    runs: dict[str, Path] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"Run spec must be label=/path, got: {spec}")
        label, path = spec.split("=", 1)
        label = label.strip()
        if not label:
            raise ValueError(f"Run label is empty: {spec}")
        if label in runs:
            raise ValueError(f"Duplicate run label: {label}")
        runs[label] = Path(path).expanduser().resolve()
    return runs


def choose_device(requested: str) -> torch.device:
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is not available.")
        return torch.device("cuda")
    if requested == "auto" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def build_model(device: torch.device) -> tuple[Any, Any]:
    from torchvision.models.detection import (
        FasterRCNN_MobileNet_V3_Large_320_FPN_Weights as Weights,
        fasterrcnn_mobilenet_v3_large_320_fpn,
    )

    weights = Weights.DEFAULT
    model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights)
    model.to(device)
    model.eval()
    return model, weights


def weight_cache_path(weights: Any) -> Path:
    filename = weights.url.rsplit("/", 1)[-1]
    return Path(torch.hub.get_dir()) / "checkpoints" / filename


def center_overlap_fraction(x1: float, x2: float, width: int) -> float:
    center_left = width * 0.42
    center_right = width * 0.58
    overlap = max(0.0, min(x2, center_right) - max(x1, center_left))
    return float(overlap / max(1.0, x2 - x1))


def box_iou(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    if a is None or b is None:
        return None
    ax1, ay1, ax2, ay2 = a["bbox_xyxy"]
    bx1, by1, bx2, by2 = b["bbox_xyxy"]
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return float(intersection / union) if union > 0.0 else None


def detection_feature(
    box: np.ndarray,
    label: str,
    score: float,
    image_shape: tuple[int, int],
) -> dict[str, Any]:
    height, width = image_shape
    x1, y1, x2, y2 = [float(item) for item in box]
    x1 = max(0.0, min(float(width), x1))
    x2 = max(0.0, min(float(width), x2))
    y1 = max(0.0, min(float(height), y1))
    y2 = max(0.0, min(float(height), y2))
    bbox_area_fraction = float(
        max(0.0, x2 - x1) * max(0.0, y2 - y1) / (height * width)
    )
    overlap = center_overlap_fraction(x1, x2, width)
    bottom_fraction = float(y2 / height)
    risk_proxy = float(
        score
        * (
            2.5 * overlap
            + 1.2 * bottom_fraction
            + 4.0 * np.sqrt(max(0.0, bbox_area_fraction))
        )
    )
    center_path_risk_proxy = risk_proxy if overlap > 0.0 else 0.0
    return {
        "label": label,
        "score": float(score),
        "bbox_xyxy": [x1, y1, x2, y2],
        "bbox_area_fraction": bbox_area_fraction,
        "center_overlap_fraction": overlap,
        "bottom_fraction": bottom_fraction,
        "risk_proxy": risk_proxy,
        "center_path_risk_proxy": center_path_risk_proxy,
    }


def run_detector(
    model: Any,
    weights: Any,
    image: np.ndarray,
    camera: str,
    score_threshold: float,
    device: torch.device,
) -> list[dict[str, Any]]:
    del camera
    tensor = to_tensor(image).to(device)
    with torch.no_grad():
        output = model([tensor])[0]
    categories = weights.meta["categories"]
    detections = []
    height, width = image.shape[:2]
    for box, label_index, score in zip(
        output["boxes"].detach().cpu().numpy(),
        output["labels"].detach().cpu().numpy(),
        output["scores"].detach().cpu().numpy(),
        strict=True,
    ):
        label = categories[int(label_index)]
        score_f = float(score)
        if label not in ROAD_CLASSES or score_f < score_threshold:
            continue
        detections.append(
            detection_feature(box, label, score_f, (height, width))
        )
    detections.sort(key=lambda item: item["risk_proxy"], reverse=True)
    return detections


def frame_row(
    frame_index: int,
    timestamp_s: float,
    detections: list[dict[str, Any]],
    prev_top: dict[str, Any] | None,
    prev_center: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    center_candidates = [
        det for det in detections if det["center_path_risk_proxy"] > 0.0
    ]
    center_candidates.sort(
        key=lambda item: item["center_path_risk_proxy"],
        reverse=True,
    )
    top = detections[0] if detections else None
    center_top = center_candidates[0] if center_candidates else None
    row = {
        "frame_index": frame_index,
        "timestamp_s": timestamp_s,
        "detection_count": len(detections),
        "center_path_detection_count": len(center_candidates),
        "top_label": top["label"] if top else None,
        "top_score": top["score"] if top else 0.0,
        "top_bbox_area_fraction": top["bbox_area_fraction"] if top else 0.0,
        "top_center_overlap_fraction": (
            top["center_overlap_fraction"] if top else 0.0
        ),
        "top_risk_proxy": top["risk_proxy"] if top else 0.0,
        "top_iou_to_prev": box_iou(prev_top, top),
        "center_top_label": center_top["label"] if center_top else None,
        "center_top_score": center_top["score"] if center_top else 0.0,
        "center_top_bbox_area_fraction": (
            center_top["bbox_area_fraction"] if center_top else 0.0
        ),
        "center_top_overlap_fraction": (
            center_top["center_overlap_fraction"] if center_top else 0.0
        ),
        "center_top_risk_proxy": (
            center_top["center_path_risk_proxy"] if center_top else 0.0
        ),
        "center_top_iou_to_prev": box_iou(prev_center, center_top),
        "detections": detections,
    }
    return row, top, center_top


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    detected = [row for row in rows if row["detection_count"] > 0]
    center_detected = [
        row for row in rows if row["center_path_detection_count"] > 0
    ]
    top_ious = [
        float(row["top_iou_to_prev"])
        for row in rows
        if row["top_iou_to_prev"] is not None
    ]
    center_ious = [
        float(row["center_top_iou_to_prev"])
        for row in rows
        if row["center_top_iou_to_prev"] is not None
    ]
    return {
        "frame_count": len(rows),
        "detected_frame_count": len(detected),
        "center_detected_frame_count": len(center_detected),
        "first_detected_s": float(detected[0]["timestamp_s"]) if detected else None,
        "first_center_detected_s": (
            float(center_detected[0]["timestamp_s"]) if center_detected else None
        ),
        "peak_top_score": float(max((row["top_score"] for row in rows), default=0.0)),
        "peak_top_risk_proxy": float(
            max((row["top_risk_proxy"] for row in rows), default=0.0)
        ),
        "peak_center_risk_proxy": float(
            max((row["center_top_risk_proxy"] for row in rows), default=0.0)
        ),
        "peak_top_bbox_area_fraction": float(
            max((row["top_bbox_area_fraction"] for row in rows), default=0.0)
        ),
        "peak_center_bbox_area_fraction": float(
            max(
                (row["center_top_bbox_area_fraction"] for row in rows),
                default=0.0,
            )
        ),
        "maximum_detection_count": int(
            max((row["detection_count"] for row in rows), default=0)
        ),
        "maximum_center_path_detection_count": int(
            max((row["center_path_detection_count"] for row in rows), default=0)
        ),
        "presence_stability": float(len(detected) / len(rows)) if rows else 0.0,
        "center_presence_stability": (
            float(len(center_detected) / len(rows)) if rows else 0.0
        ),
        "mean_top_iou_to_prev": float(np.mean(top_ious)) if top_ious else None,
        "mean_center_iou_to_prev": (
            float(np.mean(center_ious)) if center_ious else None
        ),
    }


def causal_checks(summaries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []

    def has(*labels: str) -> bool:
        return all(label in summaries for label in labels)

    if has("front_far", "front_near"):
        far = summaries["front_far"]
        near = summaries["front_near"]
        checks.append(
            {
                "id": "detector_distance_response_front_near_vs_far",
                "expected": "closer same-lane vehicle should increase detector center-path risk and apparent box scale",
                "observed": {
                    "front_far_peak_center_risk": far["peak_center_risk_proxy"],
                    "front_near_peak_center_risk": near["peak_center_risk_proxy"],
                    "front_far_peak_center_bbox_area": far[
                        "peak_center_bbox_area_fraction"
                    ],
                    "front_near_peak_center_bbox_area": near[
                        "peak_center_bbox_area_fraction"
                    ],
                },
                "decision": (
                    "accepted"
                    if near["peak_center_risk_proxy"]
                    > far["peak_center_risk_proxy"]
                    and near["peak_center_bbox_area_fraction"]
                    > far["peak_center_bbox_area_fraction"]
                    else "rejected"
                ),
            }
        )

    if has("front_near", "adjacent_near"):
        front = summaries["front_near"]
        adjacent = summaries["adjacent_near"]
        checks.append(
            {
                "id": "detector_lane_relation_front_vs_adjacent",
                "expected": "same-lane near vehicle should outrank adjacent-lane vehicle on center-path detector risk",
                "observed": {
                    "front_near_peak_center_risk": front[
                        "peak_center_risk_proxy"
                    ],
                    "adjacent_near_peak_center_risk": adjacent[
                        "peak_center_risk_proxy"
                    ],
                    "front_near_center_presence": front[
                        "center_presence_stability"
                    ],
                    "adjacent_near_center_presence": adjacent[
                        "center_presence_stability"
                    ],
                },
                "decision": (
                    "accepted"
                    if front["peak_center_risk_proxy"]
                    > adjacent["peak_center_risk_proxy"]
                    and front["center_presence_stability"]
                    > adjacent["center_presence_stability"]
                    else "down-weighted"
                ),
            }
        )

    if has("front_far", "multicar_merge"):
        far = summaries["front_far"]
        merge = summaries["multicar_merge"]
        checks.append(
            {
                "id": "detector_multicar_prominence",
                "expected": "multi-car merge should increase detector count and center-path risk relative to far-front control",
                "observed": {
                    "front_far_peak_center_risk": far["peak_center_risk_proxy"],
                    "multicar_peak_center_risk": merge[
                        "peak_center_risk_proxy"
                    ],
                    "front_far_max_detections": far["maximum_detection_count"],
                    "multicar_max_detections": merge["maximum_detection_count"],
                },
                "decision": (
                    "accepted"
                    if merge["peak_center_risk_proxy"]
                    > far["peak_center_risk_proxy"]
                    and merge["maximum_detection_count"]
                    > far["maximum_detection_count"]
                    else "down-weighted"
                ),
            }
        )

    if "no_actor" in summaries:
        no_actor = summaries["no_actor"]
        checks.append(
            {
                "id": "detector_background_response",
                "expected": "no-actor baseline may still contain native/background road-object detections and must not be treated as zero perception input",
                "observed": {
                    "no_actor_detected_frames": no_actor[
                        "detected_frame_count"
                    ],
                    "no_actor_peak_top_risk": no_actor["peak_top_risk_proxy"],
                    "no_actor_peak_center_risk": no_actor[
                        "peak_center_risk_proxy"
                    ],
                },
                "decision": (
                    "accepted"
                    if no_actor["detected_frame_count"] > 0
                    else "rejected"
                ),
            }
        )

    return checks


def write_csv(path: Path, rows_by_run: dict[str, list[dict[str, Any]]]) -> None:
    fieldnames = [
        "run_label",
        "frame_index",
        "timestamp_s",
        "detection_count",
        "center_path_detection_count",
        "top_label",
        "top_score",
        "top_bbox_area_fraction",
        "top_center_overlap_fraction",
        "top_risk_proxy",
        "top_iou_to_prev",
        "center_top_label",
        "center_top_score",
        "center_top_bbox_area_fraction",
        "center_top_overlap_fraction",
        "center_top_risk_proxy",
        "center_top_iou_to_prev",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for label, rows in rows_by_run.items():
            for row in rows:
                writer.writerow(
                    {
                        "run_label": label,
                        **{key: row[key] for key in fieldnames if key != "run_label"},
                    }
                )


def draw_detections(image: np.ndarray, row: dict[str, Any], label: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    band_height = 34
    canvas = np.zeros(
        (image.shape[0] + band_height, image.shape[1], 3),
        dtype=np.uint8,
    )
    canvas[band_height:] = image
    pil_image = Image.fromarray(canvas)
    draw = ImageDraw.Draw(pil_image)
    draw.text(
        (8, 8),
        (
            f"{label} t={row['timestamp_s']:.2f}s "
            f"C={row['center_top_risk_proxy']:.2f} "
            f"N={row['detection_count']}"
        ),
        fill=(255, 255, 255),
    )
    for detection in row["detections"][:6]:
        x1, y1, x2, y2 = detection["bbox_xyxy"]
        y1 += band_height
        y2 += band_height
        color = (
            (255, 80, 40)
            if detection["center_path_risk_proxy"] > 0.0
            else (80, 180, 255)
        )
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        draw.text(
            (x1 + 3, max(band_height, y1 - 14)),
            f"{detection['label']} {detection['score']:.2f}",
            fill=color,
        )
    return np.asarray(pil_image)


def make_response_plot(
    path: Path,
    rows_by_run: dict[str, list[dict[str, Any]]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    colors = {
        "no_actor": "black",
        "front_far": "tab:blue",
        "front_near": "tab:red",
        "adjacent_near": "tab:green",
        "multicar_merge": "tab:orange",
    }
    for label, rows in rows_by_run.items():
        times = [row["timestamp_s"] for row in rows]
        color = colors.get(label)
        axes[0, 0].plot(
            times,
            [row["center_top_risk_proxy"] for row in rows],
            linewidth=2,
            label=label,
            color=color,
        )
        axes[0, 1].plot(
            times,
            [row["top_score"] for row in rows],
            linewidth=2,
            label=label,
            color=color,
        )
        axes[1, 0].plot(
            times,
            [row["center_top_bbox_area_fraction"] for row in rows],
            linewidth=2,
            label=label,
            color=color,
        )
        axes[1, 1].step(
            times,
            [row["detection_count"] for row in rows],
            where="post",
            linewidth=2,
            label=label,
            color=color,
        )
    axes[0, 0].set_title("Center-path detector risk")
    axes[0, 0].set_ylabel("risk proxy")
    axes[0, 1].set_title("Top road-object confidence")
    axes[0, 1].set_ylabel("confidence")
    axes[1, 0].set_title("Center-path detected box scale")
    axes[1, 0].set_ylabel("bbox area fraction")
    axes[1, 1].set_title("Road-object detection count")
    axes[1, 1].set_ylabel("count")
    for axis in axes.ravel():
        axis.set_xlabel("simulation time (s)")
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    figure.suptitle(
        "HUGSIM frozen camera detector response across large interventions",
        fontsize=15,
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)


def make_contact_sheet(
    path: Path,
    observations_by_run: dict[str, list[dict[str, Any]]],
    rows_by_run: dict[str, list[dict[str, Any]]],
    camera: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = list(observations_by_run)
    frame_count = min(len(items) for items in observations_by_run.values())
    frame_indices = sorted(
        {0, frame_count // 3, (2 * frame_count) // 3, frame_count - 1}
    )
    figure, axes = plt.subplots(
        len(frame_indices),
        len(labels),
        figsize=(4.2 * len(labels), 2.9 * len(frame_indices)),
        constrained_layout=True,
    )
    if len(frame_indices) == 1:
        axes = axes[np.newaxis, :]
    if len(labels) == 1:
        axes = axes[:, np.newaxis]

    for row_index, frame_index in enumerate(frame_indices):
        for col_index, label in enumerate(labels):
            rgb = observations_by_run[label][frame_index]["rgb"][camera]
            annotated = draw_detections(rgb, rows_by_run[label][frame_index], label)
            axes[row_index, col_index].imshow(annotated)
            axes[row_index, col_index].set_xticks([])
            axes[row_index, col_index].set_yticks([])
    figure.suptitle("CAM_FRONT RGB detections from frozen Faster R-CNN", fontsize=14)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def make_grid_video(
    path: Path,
    observations_by_run: dict[str, list[dict[str, Any]]],
    rows_by_run: dict[str, list[dict[str, Any]]],
    camera: str,
) -> None:
    from moviepy import ImageSequenceClip

    labels = list(observations_by_run)
    frame_count = min(len(items) for items in observations_by_run.values())
    frames = []
    for frame_index in range(frame_count):
        tiles = [
            draw_detections(
                observations_by_run[label][frame_index]["rgb"][camera],
                rows_by_run[label][frame_index],
                label,
            )
            for label in labels
        ]
        frames.append(np.concatenate(tiles, axis=1))
    ImageSequenceClip(frames, fps=4).write_videofile(str(path), logger=None)


def main() -> int:
    args = parse_args()
    runs = parse_run_specs(args.run)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    device = choose_device(args.device)
    model, weights = build_model(device)
    cache_path = weight_cache_path(weights)

    observations_by_run: dict[str, list[dict[str, Any]]] = {}
    rows_by_run: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    run_metadata: dict[str, dict[str, Any]] = {}
    frame_counts: set[int] = set()

    for label, run_path in runs.items():
        observations = load_pickle(run_path / "observations.pkl")
        infos = load_pickle(run_path / "infos.pkl")
        audit = load_json(run_path / "audit_summary.json")
        frame_counts.add(len(observations))
        if len(infos) != len(observations):
            raise ValueError(f"{label}: infos and observations length differ")
        if audit.get("run_status") != "complete":
            raise ValueError(f"{label}: run_status is not complete")

        prev_top = None
        prev_center = None
        rows = []
        for frame_index, (observation, info) in enumerate(
            zip(observations, infos, strict=True)
        ):
            detections = run_detector(
                model,
                weights,
                observation["rgb"][args.camera],
                args.camera,
                args.score_threshold,
                device,
            )
            row, prev_top, prev_center = frame_row(
                frame_index,
                float(info["timestamp"]),
                detections,
                prev_top,
                prev_center,
            )
            rows.append(row)
        observations_by_run[label] = observations
        rows_by_run[label] = rows
        summaries[label] = summarize_rows(rows)
        run_metadata[label] = {
            "path": str(run_path),
            "scenario_yaml": audit["source_assets"]["scenario_yaml"],
            "scenario_yaml_sha256": audit["source_assets"]["scenario_yaml_sha256"],
            "completed_steps": audit["completed_steps"],
            "hugsim_commit": audit["hugsim_commit"],
            "control_convention": audit["control_convention"],
        }

    if len(frame_counts) != 1:
        raise ValueError(f"Runs have different frame counts: {sorted(frame_counts)}")

    csv_path = output / "camera_detector_timeseries.csv"
    plot_path = output / "camera_detector_response.png"
    contact_sheet_path = output / "camera_detector_front_contact_sheet.png"
    video_path = output / "camera_detector_front_grid.mp4"
    write_csv(csv_path, rows_by_run)
    make_response_plot(plot_path, rows_by_run)
    make_contact_sheet(contact_sheet_path, observations_by_run, rows_by_run, args.camera)
    make_grid_video(video_path, observations_by_run, rows_by_run, args.camera)

    checks = causal_checks(summaries)
    summary = {
        "receiver_contract": {
            "name": "torchvision_fasterrcnn_mobilenet_v3_large_320_fpn_coco_v1",
            "input": {
                "camera": args.camera,
                "modalities": ["rgb"],
                "road_classes": list(ROAD_CLASSES),
                "score_threshold": args.score_threshold,
            },
            "weights": {
                "enum": str(weights),
                "url": weights.url,
                "cache_path": str(cache_path),
                "sha256": sha256(cache_path),
            },
            "device": str(device),
            "status": "frozen_camera_only_detector_not_full_ad_stack",
            "scope": (
                "Runs a COCO-pretrained RGB detector and reports boxes, "
                "confidence, simple image-plane tracking, and risk-ordering "
                "proxies. It cannot establish planning, control, real-sensor "
                "consistency, or complete AD behavior."
            ),
        },
        "runs": run_metadata,
        "summaries": summaries,
        "causal_checks": checks,
        "overall_decision": (
            "down-weighted"
            if any(check["decision"] != "rejected" for check in checks)
            else "rejected"
        ),
        "artifacts": {
            "timeseries_csv": str(csv_path),
            "response_plot": str(plot_path),
            "front_contact_sheet": str(contact_sheet_path),
            "front_grid_video": str(video_path),
        },
    }
    with (output / "camera_detector_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(jsonable(summary), stream, indent=2)
    print(json.dumps(jsonable(summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
