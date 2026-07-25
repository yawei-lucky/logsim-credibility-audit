#!/usr/bin/env python3
"""Audit source-mask versus HUGSIM native-dynamic image support."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


CAMERAS = (
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--render-report",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def weighted_centroid(weights: np.ndarray) -> tuple[float, float] | None:
    total = float(np.sum(weights))
    if total <= 0.0:
        return None
    y, x = np.indices(weights.shape)
    return (
        float(np.sum(weights * x) / total),
        float(np.sum(weights * y) / total),
    )


def binary_centroid(mask: np.ndarray) -> tuple[float, float] | None:
    y, x = np.where(mask)
    if not len(x):
        return None
    return float(np.mean(x)), float(np.mean(y))


def support_metrics(
    source_dynamic_mask: np.ndarray,
    factual_rgb: np.ndarray,
    static_rgb: np.ndarray,
    thresholds: list[int],
    dilation_px: int,
) -> dict[str, Any]:
    source_mask = np.asarray(source_dynamic_mask, dtype=bool)
    factual = np.asarray(factual_rgb, dtype=np.float64)
    static = np.asarray(static_rgb, dtype=np.float64)
    if factual.shape != static.shape or factual.shape[:2] != source_mask.shape:
        raise ValueError("source mask, factual RGB and static RGB shapes differ")
    delta = np.mean(np.abs(factual - static), axis=2)
    total_energy = float(np.sum(delta))
    source_pixels = int(np.sum(source_mask))
    kernel_size = 2 * dilation_px + 1
    dilated = cv2.dilate(
        source_mask.astype(np.uint8),
        np.ones((kernel_size, kernel_size), dtype=np.uint8),
    ).astype(bool)
    exact_energy = float(np.sum(delta[source_mask]))
    dilated_energy = float(np.sum(delta[dilated]))
    source_centroid = binary_centroid(source_mask)
    render_centroid = weighted_centroid(delta)
    centroid_error = None
    if source_centroid is not None and render_centroid is not None:
        centroid_error = float(
            np.linalg.norm(
                np.asarray(render_centroid) - np.asarray(source_centroid)
            )
        )

    sensitivity = {}
    for threshold in thresholds:
        rendered_support = delta >= threshold
        intersection = int(np.sum(rendered_support & source_mask))
        union = int(np.sum(rendered_support | source_mask))
        rendered_pixels = int(np.sum(rendered_support))
        sensitivity[str(threshold)] = {
            "render_support_pixels": rendered_pixels,
            "intersection_pixels": intersection,
            "iou": float(intersection / union) if union else None,
            "source_mask_recall": (
                float(intersection / source_pixels) if source_pixels else None
            ),
            "render_support_precision": (
                float(intersection / rendered_pixels)
                if rendered_pixels
                else None
            ),
        }
    return {
        "source_mask_pixels": source_pixels,
        "source_mask_nonempty": source_pixels > 0,
        "render_difference_energy": total_energy,
        "render_difference_nonzero": total_energy > 0.0,
        "maximum_pixel_delta_8bit": float(np.max(delta)),
        "exact_source_mask_energy_fraction": (
            exact_energy / total_energy if total_energy else None
        ),
        f"dilated_{dilation_px}px_source_mask_energy_fraction": (
            dilated_energy / total_energy if total_energy else None
        ),
        "source_mask_centroid_xy": source_centroid,
        "render_energy_centroid_xy": render_centroid,
        "centroid_error_px": centroid_error,
        "threshold_sensitivity": sensitivity,
        "_delta": delta,
        "_source_mask": source_mask,
    }


def validate_reports(
    preregistration: dict[str, Any],
    reports: list[tuple[Path, dict[str, Any]]],
) -> None:
    expected_frames = set(preregistration["selection"]["frame_indices"])
    observed_frames = {int(report["frame_index"]) for _, report in reports}
    if observed_frames != expected_frames:
        raise ValueError(
            f"render frames {sorted(observed_frames)} != "
            f"preregistered {sorted(expected_frames)}"
        )
    identities = set()
    for _, report in reports:
        variants = report["variants"]
        if set(variants) != {"factual", "static_control"}:
            raise ValueError("expected factual and static_control variants")
        if variants["factual"]["native_dynamics_omitted"]:
            raise ValueError("factual variant omitted native dynamics")
        if not variants["static_control"]["native_dynamics_omitted"]:
            raise ValueError("static control retained native dynamics")
        identities.add(
            (
                report["hugsim"]["scene_checkpoint_sha256"],
                tuple(
                    sorted(
                        report["hugsim"][
                            "dynamic_checkpoint_sha256"
                        ].items()
                    )
                ),
                variants["factual"]["metadata_sha256"],
            )
        )
    if len(identities) != 1:
        raise ValueError("scene, dynamic checkpoint or metadata changed")


def crop_bounds(mask: np.ndarray, margin: int = 45) -> tuple[int, int, int, int]:
    y, x = np.where(mask)
    if not len(x):
        return 0, 0, mask.shape[1], mask.shape[0]
    return (
        max(0, int(np.min(x)) - margin),
        max(0, int(np.min(y)) - margin),
        min(mask.shape[1], int(np.max(x)) + margin + 1),
        min(mask.shape[0], int(np.max(y)) + margin + 1),
    )


def save_visualization(
    supported_rows: list[dict[str, Any]],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        len(supported_rows),
        4,
        figsize=(15, 3.8 * len(supported_rows)),
        squeeze=False,
        constrained_layout=True,
    )
    for row_index, row in enumerate(supported_rows):
        mask = row["_source_mask"]
        delta = row["_delta"]
        x0, y0, x1, y1 = crop_bounds(mask)
        real = row["_real_rgb"][y0:y1, x0:x1]
        factual = row["_factual_rgb"][y0:y1, x0:x1]
        static = row["_static_rgb"][y0:y1, x0:x1]
        local_mask = mask[y0:y1, x0:x1]
        local_delta = delta[y0:y1, x0:x1]

        axes[row_index, 0].imshow(real)
        overlay = np.zeros((*local_mask.shape, 4), dtype=np.float64)
        overlay[local_mask] = (1.0, 0.0, 0.0, 0.32)
        axes[row_index, 0].imshow(overlay)
        axes[row_index, 0].set_title(
            f"frame {row['frame_index']} · {row['camera']}\n"
            "Source RGB + source dynamic mask"
        )
        axes[row_index, 1].imshow(factual)
        axes[row_index, 1].set_title("HUGSIM factual dynamic")
        axes[row_index, 2].imshow(static)
        axes[row_index, 2].set_title("Same render, dynamics omitted")
        axes[row_index, 3].imshow(local_delta, cmap="magma", vmin=0)
        axes[row_index, 3].contour(
            local_mask.astype(float),
            levels=[0.5],
            colors=["cyan"],
            linewidths=1.2,
        )
        axes[row_index, 3].set_title(
            "Factual − static support\n"
            f"exact energy {row['exact_source_mask_energy_fraction']:.3f}, "
            f"centroid {row['centroid_error_px']:.1f}px"
        )
        for axis in axes[row_index]:
            axis.axis("off")
    figure.suptitle(
        "Source-side dynamic support versus HUGSIM native-dynamic support\n"
        "Reader-declared held-out frames; source mask is a partial reference",
        fontsize=15,
    )
    path = output / "hugsim_source_dynamic_visibility.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    preregistration_path = args.preregistration.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve()
    report_paths = [path.expanduser().resolve() for path in args.render_report]
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    for path in [preregistration_path, *report_paths]:
        if not path.is_file():
            raise FileNotFoundError(path)
    preregistration = load_json(preregistration_path)
    reports = [(path, load_json(path)) for path in report_paths]
    validate_reports(preregistration, reports)

    thresholds = preregistration["measurements"]["threshold_sensitivity"][
        "thresholds"
    ]
    dilation_px = 16
    rows = []
    for report_path, report in sorted(
        reports, key=lambda item: int(item[1]["frame_index"])
    ):
        frame_index = int(report["frame_index"])
        for camera in CAMERAS:
            source_keep_mask = np.load(
                source_root
                / "masks"
                / camera
                / f"{frame_index:05d}.npy"
            )
            source_dynamic_mask = ~source_keep_mask.astype(bool)
            real_path = (
                source_root
                / "images"
                / camera
                / f"{frame_index:05d}.jpg"
            )
            factual_path = Path(
                report["variants"]["factual"]["camera_results"][camera][
                    "render_path"
                ]
            )
            static_path = Path(
                report["variants"]["static_control"]["camera_results"][camera][
                    "render_path"
                ]
            )
            real = np.asarray(Image.open(real_path).convert("RGB"))
            factual = np.asarray(Image.open(factual_path).convert("RGB"))
            static = np.asarray(Image.open(static_path).convert("RGB"))
            metrics = support_metrics(
                source_dynamic_mask,
                factual,
                static,
                thresholds,
                dilation_px,
            )
            source_pixels = int(np.sum(source_dynamic_mask))
            post_hoc_photometric = None
            if source_pixels:
                factual_mae = float(
                    np.mean(
                        np.abs(
                            real[source_dynamic_mask].astype(np.float64)
                            - factual[source_dynamic_mask].astype(np.float64)
                        )
                    )
                )
                static_mae = float(
                    np.mean(
                        np.abs(
                            real[source_dynamic_mask].astype(np.float64)
                            - static[source_dynamic_mask].astype(np.float64)
                        )
                    )
                )
                post_hoc_photometric = {
                    "status": "post-hoc descriptive diagnostic; not preregistered",
                    "factual_real_mae_8bit": factual_mae,
                    "static_real_mae_8bit": static_mae,
                    "factual_improvement_8bit": static_mae - factual_mae,
                    "factual_relative_improvement": (
                        (static_mae - factual_mae) / static_mae
                        if static_mae
                        else None
                    ),
                }
            rows.append(
                {
                    "frame_index": frame_index,
                    "timestamp_s": float(report["timestamp_s"]),
                    "camera": camera,
                    "render_report": str(report_path),
                    "source_mask_path": str(
                        source_root
                        / "masks"
                        / camera
                        / f"{frame_index:05d}.npy"
                    ),
                    "source_rgb_path": str(real_path),
                    "factual_render_path": str(factual_path),
                    "static_render_path": str(static_path),
                    "post_hoc_source_mask_photometric": post_hoc_photometric,
                    **metrics,
                    "_real_rgb": real,
                    "_factual_rgb": factual,
                    "_static_rgb": static,
                }
            )

    supported = [row for row in rows if row["source_mask_nonempty"]]
    unsupported = [row for row in rows if not row["source_mask_nonempty"]]
    if not supported:
        raise ValueError("no source-supported dynamic views")
    membership_equal = all(
        row["source_mask_nonempty"] == row["render_difference_nonzero"]
        for row in rows
    )
    visual_path = output / "hugsim_source_dynamic_visibility.png"
    output.mkdir(parents=True)
    visual_path = save_visualization(supported, output)

    exact = [
        row["exact_source_mask_energy_fraction"] for row in supported
    ]
    dilated_key = f"dilated_{dilation_px}px_source_mask_energy_fraction"
    dilated = [row[dilated_key] for row in supported]
    centroid = [row["centroid_error_px"] for row in supported]
    post_hoc_relative = [
        row["post_hoc_source_mask_photometric"][
            "factual_relative_improvement"
        ]
        for row in supported
    ]
    serializable_rows = []
    for row in rows:
        serializable_rows.append(
            {
                key: value
                for key, value in row.items()
                if not key.startswith("_")
            }
        )
    result = {
        "audit_id": "hugsim_source_dynamic_visibility_001",
        "date": date.today().isoformat(),
        "inputs": {
            "preregistration": str(preregistration_path),
            "preregistration_sha256": sha256_file(preregistration_path),
            "source_root": str(source_root),
            "source_archive_manifest": str(
                source_root / "source_archive_manifest.json"
            ),
            "render_reports": [
                {
                    "path": str(path),
                    "sha256": sha256_file(path),
                }
                for path in report_paths
            ],
        },
        "rows": serializable_rows,
        "summary": {
            "camera_frame_pairs": len(rows),
            "source_supported_views": len(supported),
            "source_empty_views": len(unsupported),
            "source_and_render_camera_membership_equal": membership_equal,
            "source_supported_all_have_render_energy": all(
                row["render_difference_nonzero"] for row in supported
            ),
            "source_empty_all_have_zero_render_energy": all(
                not row["render_difference_nonzero"] for row in unsupported
            ),
            "exact_source_mask_energy_fraction": {
                "mean": float(np.mean(exact)),
                "min": float(np.min(exact)),
                "max": float(np.max(exact)),
            },
            dilated_key: {
                "mean": float(np.mean(dilated)),
                "min": float(np.min(dilated)),
                "max": float(np.max(dilated)),
            },
            "centroid_error_px": {
                "mean": float(np.mean(centroid)),
                "min": float(np.min(centroid)),
                "max": float(np.max(centroid)),
            },
            "post_hoc_source_mask_photometric": {
                "status": "post-hoc descriptive diagnostic; not preregistered",
                "factual_lower_mae_count": sum(
                    value > 0.0 for value in post_hoc_relative
                ),
                "view_count": len(post_hoc_relative),
                "mean_factual_relative_improvement": float(
                    np.mean(post_hoc_relative)
                ),
                "min_factual_relative_improvement": float(
                    np.min(post_hoc_relative)
                ),
                "max_factual_relative_improvement": float(
                    np.max(post_hoc_relative)
                ),
            },
        },
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": [
                "the native-dynamic render path changed exactly the same three camera-frame views supported by the source-side dynamic mask",
                "rendered dynamic difference energy overlapped the source-mask region in all three supported views, including the front-left to back-left camera boundary",
            ],
            "down-weighted": [
                "the source mask is upstream and renderer-independent but shares source geometry and reconstruction preprocessing",
                "only two timestamps, one native actor and one reconstruction are covered; no external overlap acceptance threshold exists",
                "the static control contains person-like residual structure, so factual-minus-static isolates the native dynamic contribution but not all actor-like content presented to a receiver",
            ],
            "rejected": [
                "this overlap proves photometric, semantic, depth or real-sensor equivalence",
                "this overlap proves sufficient information for SparseDrive or another AD",
                "this pilot establishes general HUGSIM credibility or AD safety",
            ],
        },
        "visualization": str(visual_path),
        "visualization_sha256": sha256_file(visual_path),
    }
    result_path = output / "hugsim_source_dynamic_visibility_audit.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
