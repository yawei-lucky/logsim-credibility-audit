#!/usr/bin/env python3
"""Compare declared HUGSIM actor projection with its RGB difference support."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from render_hugsim_exact_source_pose import CAMERAS, select_camera_records, sha256_file


def project_world_points(
    world_points: np.ndarray,
    camtoworld: np.ndarray,
    intrinsics: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(world_points, dtype=np.float64)
    c2w = np.asarray(camtoworld, dtype=np.float64)
    intrinsic = np.asarray(intrinsics, dtype=np.float64)[:3, :3]
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("world points must have shape (N,3)")
    if c2w.shape != (4, 4) or intrinsic.shape != (3, 3):
        raise ValueError("invalid camera transform or intrinsics")
    camera_points = (np.linalg.inv(c2w)[:3, :3] @ points.T).T + np.linalg.inv(c2w)[:3, 3]
    image_homogeneous = (intrinsic @ camera_points.T).T
    depth = camera_points[:, 2]
    pixels = image_homogeneous[:, :2] / np.maximum(depth[:, None], 1e-9)
    return pixels, depth


def transform_actor_points(local_points: np.ndarray, actor_to_world: np.ndarray) -> np.ndarray:
    points = np.asarray(local_points, dtype=np.float64)
    transform = np.asarray(actor_to_world, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or transform.shape != (4, 4):
        raise ValueError("invalid actor points or transform")
    return (transform[:3, :3] @ points.T).T + transform[:3, 3]


def difference_support(
    baseline_rgb: np.ndarray, actor_rgb: np.ndarray, threshold_8bit: int
) -> tuple[np.ndarray, np.ndarray]:
    baseline = np.asarray(baseline_rgb, dtype=np.int16)
    actor = np.asarray(actor_rgb, dtype=np.int16)
    if baseline.shape != actor.shape or baseline.ndim != 3:
        raise ValueError("baseline and actor RGB shapes differ")
    delta = np.max(np.abs(actor - baseline), axis=2)
    return delta >= threshold_8bit, delta


def enclosing_box(mask: np.ndarray) -> list[int] | None:
    y, x = np.where(mask)
    if not len(x):
        return None
    return [int(np.min(x)), int(np.min(y)), int(np.max(x)), int(np.max(y))]


def box_iou(left: list[int] | None, right: list[int] | None) -> float | None:
    if left is None or right is None:
        return None
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0, x1 - x0 + 1) * max(0, y1 - y0 + 1)
    left_area = (left[2] - left[0] + 1) * (left[3] - left[1] + 1)
    right_area = (right[2] - right[0] + 1) * (right[3] - right[1] + 1)
    union = left_area + right_area - intersection
    return float(intersection / union) if union else None


def projection_support_mask(
    pixels: np.ndarray,
    depth: np.ndarray,
    image_shape: tuple[int, int],
    dilation_px: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    height, width = image_shape
    valid = np.isfinite(pixels).all(axis=1) & np.isfinite(depth) & (depth > 0.01)
    points = pixels[valid]
    if len(points) < 3:
        empty = np.zeros((height, width), dtype=bool)
        return empty, empty, int(len(points))
    hull = cv2.convexHull(np.rint(points).astype(np.int32))
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, hull, 1)
    kernel = np.ones((2 * dilation_px + 1, 2 * dilation_px + 1), dtype=np.uint8)
    dilated = cv2.dilate(mask, kernel)
    return mask.astype(bool), dilated.astype(bool), int(len(points))


def alignment_metrics(
    projected_mask: np.ndarray,
    dilated_projected_mask: np.ndarray,
    difference_mask: np.ndarray,
    minimum_difference_pixels: int,
    minimum_difference_coverage: float,
    maximum_centroid_error_px: float,
) -> dict[str, Any]:
    difference_pixels = int(np.count_nonzero(difference_mask))
    projected_pixels = int(np.count_nonzero(projected_mask))
    visible = difference_pixels >= minimum_difference_pixels
    overlap = int(np.count_nonzero(difference_mask & dilated_projected_mask))
    coverage = float(overlap / difference_pixels) if difference_pixels else None
    difference_box = enclosing_box(difference_mask)
    projected_box = enclosing_box(projected_mask)
    centroid_error = None
    if difference_box is not None and projected_box is not None:
        difference_center = np.asarray(
            [(difference_box[0] + difference_box[2]) / 2, (difference_box[1] + difference_box[3]) / 2]
        )
        projected_center = np.asarray(
            [(projected_box[0] + projected_box[2]) / 2, (projected_box[1] + projected_box[3]) / 2]
        )
        centroid_error = float(np.linalg.norm(difference_center - projected_center))
    passed = (
        not visible
        or (
            projected_pixels > 0
            and coverage is not None
            and coverage >= minimum_difference_coverage
            and centroid_error is not None
            and centroid_error <= maximum_centroid_error_px
        )
    )
    return {
        "rgb_difference_visible": visible,
        "rgb_difference_pixels": difference_pixels,
        "projected_hull_pixels": projected_pixels,
        "difference_pixels_inside_dilated_projection": overlap,
        "difference_support_coverage": coverage,
        "difference_bbox_xyxy": difference_box,
        "projected_gaussian_centre_bbox_xyxy": projected_box,
        "bbox_iou": box_iou(difference_box, projected_box),
        "bbox_centroid_error_px": centroid_error,
        "passed": passed,
    }


def load_actor_points(checkpoint: Path) -> np.ndarray:
    import torch

    saved, _ = torch.load(checkpoint, map_location="cpu", weights_only=False)
    points = saved[1].detach().cpu().numpy().astype(np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("actor checkpoint has invalid Gaussian centres")
    return points


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--render-report", type=Path, required=True)
    parser.add_argument("--frame-index", type=int, required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--actor-checkpoint", type=Path, required=True)
    parser.add_argument("--baseline-label", default="factual")
    parser.add_argument("--actor-label", default="actor")
    parser.add_argument("--difference-threshold", type=int, default=5)
    parser.add_argument("--projection-dilation-px", type=int, default=8)
    parser.add_argument("--minimum-difference-pixels", type=int, default=40)
    parser.add_argument("--minimum-difference-coverage", type=float, default=0.85)
    parser.add_argument("--maximum-centroid-error-px", type=float, default=24.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata_path = args.metadata.expanduser().resolve()
    report_path = args.render_report.expanduser().resolve()
    actor_checkpoint = args.actor_checkpoint.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (metadata_path, report_path, actor_checkpoint):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    if not 0 < args.difference_threshold <= 255:
        raise ValueError("difference threshold must be in 1..255")
    if not 0.0 <= args.minimum_difference_coverage <= 1.0:
        raise ValueError("minimum difference coverage must be in 0..1")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = select_camera_records(metadata, args.frame_index)
    if int(report["frame_index"]) != args.frame_index:
        raise ValueError("render report frame does not match requested frame")
    variants = report["variants"]
    if args.baseline_label not in variants or args.actor_label not in variants:
        raise ValueError("render report lacks requested baseline or actor variant")
    if variants[args.actor_label]["metadata_sha256"] != sha256_file(metadata_path):
        raise ValueError("actor render metadata differs from projection metadata")

    local_points = load_actor_points(actor_checkpoint)
    actor_transform = np.asarray(
        records["CAM_FRONT"]["dynamics"][args.actor_id], dtype=np.float64
    )
    for camera, record in records.items():
        candidate = np.asarray(record["dynamics"][args.actor_id], dtype=np.float64)
        if not np.allclose(candidate, actor_transform, atol=0.0, rtol=0.0):
            raise ValueError(f"{camera}: actor transform differs within camera group")
    world_points = transform_actor_points(local_points, actor_transform)

    output.mkdir(parents=True)
    overlay_dir = output / "overlays"
    overlay_dir.mkdir()
    rows = {}
    overlay_arrays = []
    for camera in CAMERAS:
        record = records[camera]
        baseline_path = Path(
            variants[args.baseline_label]["camera_results"][camera]["render_path"]
        )
        actor_path = Path(
            variants[args.actor_label]["camera_results"][camera]["render_path"]
        )
        baseline = np.asarray(Image.open(baseline_path).convert("RGB"))
        actor = np.asarray(Image.open(actor_path).convert("RGB"))
        difference_mask, delta = difference_support(
            baseline, actor, args.difference_threshold
        )
        pixels, depth = project_world_points(
            world_points,
            np.asarray(record["camtoworld"], dtype=np.float64),
            np.asarray(record["intrinsics"], dtype=np.float64),
        )
        projected_mask, dilated_mask, projected_count = projection_support_mask(
            pixels,
            depth,
            actor.shape[:2],
            args.projection_dilation_px,
        )
        metrics = alignment_metrics(
            projected_mask,
            dilated_mask,
            difference_mask,
            args.minimum_difference_pixels,
            args.minimum_difference_coverage,
            args.maximum_centroid_error_px,
        )
        metrics.update(
            {
                "camera": camera,
                "projected_centres_in_front_count": projected_count,
                "maximum_rgb_difference_8bit": int(np.max(delta)),
                "baseline_render": str(baseline_path),
                "actor_render": str(actor_path),
            }
        )
        overlay = actor.copy()
        contours, _ = cv2.findContours(
            projected_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cv2.drawContours(overlay, contours, -1, (0, 255, 0), 2)
        difference_box = metrics["difference_bbox_xyxy"]
        if difference_box is not None:
            cv2.rectangle(
                overlay,
                (difference_box[0], difference_box[1]),
                (difference_box[2], difference_box[3]),
                (255, 128, 0),
                2,
            )
        cv2.putText(
            overlay,
            "green=declared Gaussian projection; orange=RGB difference",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        overlay_path = overlay_dir / f"{camera}.png"
        Image.fromarray(overlay).save(overlay_path)
        metrics["overlay"] = str(overlay_path)
        rows[camera] = metrics
        overlay_arrays.append((camera, overlay))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 3, figsize=(15, 6), squeeze=False)
    for axis, (camera, overlay) in zip(axes.flat, overlay_arrays, strict=True):
        axis.imshow(overlay)
        metric = rows[camera]
        if metric["rgb_difference_visible"]:
            status = f"coverage={metric['difference_support_coverage']:.3f}, centre={metric['bbox_centroid_error_px']:.1f}px"
        else:
            status = "no material RGB difference"
        axis.set_title(f"{camera}\n{status}")
        axis.axis("off")
    figure.suptitle(
        f"HUGSIM actor projection contract — frame {args.frame_index}\n"
        "green: declared actor Gaussian-centre hull; orange: actor-minus-baseline RGB support"
    )
    figure.tight_layout()
    contact_sheet = output / "actor_projection_alignment.png"
    figure.savefig(contact_sheet, dpi=160)
    plt.close(figure)

    visible_rows = [row for row in rows.values() if row["rgb_difference_visible"]]
    overall_passed = bool(visible_rows) and all(row["passed"] for row in visible_rows)
    result = {
        "audit_id": "hugsim_actor_projection_alignment_001",
        "date": date.today().isoformat(),
        "frame_index": args.frame_index,
        "timestamp_s": float(records["CAM_FRONT"]["timestamp"]),
        "actor_id": args.actor_id,
        "actor_checkpoint": str(actor_checkpoint),
        "actor_checkpoint_sha256": sha256_file(actor_checkpoint),
        "actor_gaussian_centre_count": int(len(local_points)),
        "metadata": str(metadata_path),
        "metadata_sha256": sha256_file(metadata_path),
        "render_report": str(report_path),
        "render_report_sha256": sha256_file(report_path),
        "thresholds": {
            "rgb_difference_8bit": args.difference_threshold,
            "projection_dilation_px": args.projection_dilation_px,
            "minimum_difference_pixels": args.minimum_difference_pixels,
            "minimum_difference_coverage": args.minimum_difference_coverage,
            "maximum_bbox_centroid_error_px": args.maximum_centroid_error_px,
        },
        "camera_results": rows,
        "visible_cameras": [row["camera"] for row in visible_rows],
        "overall_passed": overall_passed,
        "contact_sheet": str(contact_sheet),
        "contact_sheet_sha256": sha256_file(contact_sheet),
        "claim_boundary": (
            "Agreement links the declared transform and actor checkpoint to their "
            "own HUGSIM RGB rasterization. It detects gross transport/axis errors but "
            "does not establish metric 3D truth, source-sensor equivalence or realism."
        ),
    }
    result_path = output / "actor_projection_alignment.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0 if overall_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
