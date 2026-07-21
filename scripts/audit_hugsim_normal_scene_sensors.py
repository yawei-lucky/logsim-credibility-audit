#!/usr/bin/env python3
"""Audit HUGSIM normal-scene sensor outputs without treating them as truth.

The checks in this script establish array/calibration contract validity and
renderer-internal RGB/semantic/depth co-variation. They do not establish
real-sensor accuracy or cross-camera 3D correctness.
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


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-hugsim-normal-sensor-audit")

SEMANTIC_NAMES = {
    0: "road",
    1: "sidewalk",
    2: "building",
    3: "wall",
    4: "fence",
    5: "pole",
    6: "traffic_light",
    7: "traffic_sign",
    8: "vegetation",
    9: "terrain",
    10: "sky",
    11: "person",
    12: "rider",
    13: "car",
    14: "truck",
    15: "bus",
    16: "train",
    17: "motorcycle",
    18: "bicycle",
    255: "ignored",
}

SEMANTIC_COLORS = np.asarray(
    [
        [128, 64, 128], [244, 35, 232], [70, 70, 70], [102, 102, 156],
        [190, 153, 153], [153, 153, 153], [250, 170, 30], [220, 220, 0],
        [107, 142, 35], [152, 251, 152], [70, 130, 180], [220, 20, 60],
        [255, 0, 0], [0, 0, 142], [0, 0, 70], [0, 60, 100],
        [0, 80, 100], [0, 0, 230], [119, 11, 32],
    ],
    dtype=np.uint8,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True,
                        help="label=/absolute/or/relative/run/path")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def parse_runs(values: list[str]) -> dict[str, Path]:
    runs: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Expected label=path, got {value!r}")
        label, raw_path = value.split("=", 1)
        if not label or label in runs:
            raise ValueError(f"Invalid or duplicate label: {label!r}")
        runs[label] = Path(raw_path).expanduser().resolve()
    return runs


def load_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def edge_map(array: np.ndarray) -> np.ndarray:
    edges = np.zeros(array.shape[:2], dtype=bool)
    if array.ndim == 2:
        edges[:, 1:] |= array[:, 1:] != array[:, :-1]
        edges[1:, :] |= array[1:, :] != array[:-1, :]
    else:
        edges[:, 1:] |= np.any(array[:, 1:] != array[:, :-1], axis=2)
        edges[1:, :] |= np.any(array[1:, :] != array[:-1, :], axis=2)
    return edges


def depth_edge_map(depth: np.ndarray) -> np.ndarray:
    edges = np.zeros(depth.shape, dtype=bool)
    horizontal_abs = np.abs(depth[:, 1:] - depth[:, :-1])
    horizontal_rel = horizontal_abs / np.maximum(
        np.minimum(depth[:, 1:], depth[:, :-1]), 1e-3
    )
    vertical_abs = np.abs(depth[1:, :] - depth[:-1, :])
    vertical_rel = vertical_abs / np.maximum(
        np.minimum(depth[1:, :], depth[:-1, :]), 1e-3
    )
    edges[:, 1:] |= (horizontal_abs > 0.5) & (horizontal_rel > 0.05)
    edges[1:, :] |= (vertical_abs > 0.5) & (vertical_rel > 0.05)
    return edges


def dilate_one(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[1:, 1:] |= mask[:-1, :-1]
    out[:-1, :-1] |= mask[1:, 1:]
    out[1:, :-1] |= mask[:-1, 1:]
    out[:-1, 1:] |= mask[1:, :-1]
    return out


def rgb_gradient(rgb: np.ndarray) -> np.ndarray:
    gray = rgb.astype(np.float32).mean(axis=2) / 255.0
    gradient = np.zeros(gray.shape, dtype=np.float32)
    gradient[:, 1:] = np.maximum(gradient[:, 1:], np.abs(gray[:, 1:] - gray[:, :-1]))
    gradient[1:, :] = np.maximum(gradient[1:, :], np.abs(gray[1:, :] - gray[:-1, :]))
    return gradient


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def frame_camera_metrics(rgb: np.ndarray, semantic: np.ndarray,
                         depth: np.ndarray) -> dict[str, Any]:
    if rgb.shape[:2] != semantic.shape or semantic.shape != depth.shape:
        raise ValueError(
            f"Modality shapes differ: rgb={rgb.shape}, semantic={semantic.shape}, depth={depth.shape}"
        )
    semantic_edges = edge_map(semantic)
    depth_edges = depth_edge_map(depth)
    rgb_grad = rgb_gradient(rgb)
    semantic_edge_count = int(semantic_edges.sum())
    depth_edge_count = int(depth_edges.sum())
    semantic_dilated = dilate_one(semantic_edges)
    depth_dilated = dilate_one(depth_edges)
    sem_rgb_mean = float(rgb_grad[semantic_edges].mean()) if semantic_edge_count else 0.0
    non_sem_rgb_mean = float(rgb_grad[~semantic_dilated].mean()) if (~semantic_dilated).any() else 0.0
    counts = np.bincount(semantic.reshape(-1), minlength=256)
    fractions = counts / semantic.size
    return {
        "height": int(semantic.shape[0]),
        "width": int(semantic.shape[1]),
        "rgb_dtype": str(rgb.dtype),
        "semantic_dtype": str(semantic.dtype),
        "depth_dtype": str(depth.dtype),
        "depth_nonfinite_fraction": float((~np.isfinite(depth)).mean()),
        "depth_nonpositive_fraction": float((depth <= 0).mean()),
        "depth_p10_m": float(np.nanpercentile(depth, 10)),
        "depth_median_m": float(np.nanmedian(depth)),
        "depth_p90_m": float(np.nanpercentile(depth, 90)),
        "semantic_class_count": int((counts > 0).sum()),
        "semantic_fractions": {
            SEMANTIC_NAMES.get(i, f"id_{i}"): float(fractions[i])
            for i in np.flatnonzero(counts)
        },
        "semantic_edge_fraction": float(semantic_edges.mean()),
        "depth_edge_fraction": float(depth_edges.mean()),
        "semantic_edges_near_depth_edge_fraction": safe_ratio(
            int((semantic_edges & depth_dilated).sum()), semantic_edge_count
        ),
        "depth_edges_near_semantic_edge_fraction": safe_ratio(
            int((depth_edges & semantic_dilated).sum()), depth_edge_count
        ),
        "rgb_gradient_on_semantic_edge_mean": sem_rgb_mean,
        "rgb_gradient_off_semantic_edge_mean": non_sem_rgb_mean,
        "rgb_semantic_boundary_gradient_ratio": safe_ratio(sem_rgb_mean, non_sem_rgb_mean),
        "rgb_sha256": array_sha256(rgb),
    }


def calibration_metrics(info: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for camera, params in info["cam_params"].items():
        intrinsic = params["intrinsic"]
        v2c = np.asarray(params["v2c"], dtype=np.float64)
        rotation = v2c[:3, :3]
        height, width = observation["semantic"][camera].shape
        result[camera] = {
            "array_shape_matches_intrinsic": bool(
                height == int(intrinsic["H"]) and width == int(intrinsic["W"])
            ),
            "principal_point_in_bounds": bool(
                0 <= float(intrinsic["cx"]) <= width
                and 0 <= float(intrinsic["cy"]) <= height
            ),
            "positive_fov": bool(
                float(intrinsic["fovx"]) > 0 and float(intrinsic["fovy"]) > 0
            ),
            "rotation_orthonormal_max_error": float(
                np.abs(rotation @ rotation.T - np.eye(3)).max()
            ),
            "rotation_determinant": float(np.linalg.det(rotation)),
            "v2c": v2c.tolist(),
        }
    return result


def semantic_distribution(semantic: np.ndarray) -> np.ndarray:
    counts = np.bincount(semantic.reshape(-1), minlength=256).astype(np.float64)
    return counts / counts.sum()


def aggregate_camera(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_keys = (
        "depth_nonfinite_fraction", "depth_nonpositive_fraction", "depth_p10_m",
        "depth_median_m", "depth_p90_m", "semantic_class_count",
        "semantic_edge_fraction", "depth_edge_fraction",
        "semantic_edges_near_depth_edge_fraction",
        "depth_edges_near_semantic_edge_fraction",
        "rgb_gradient_on_semantic_edge_mean",
        "rgb_gradient_off_semantic_edge_mean",
        "rgb_semantic_boundary_gradient_ratio",
    )
    result: dict[str, Any] = {}
    for key in numeric_keys:
        values = [float(row[key]) for row in rows if row[key] is not None]
        result[key] = {
            "mean": float(np.mean(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }
    return result


def analyze_run(label: str, run_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[Any]]:
    observations = load_pickle(run_path / "observations.pkl")
    infos = load_pickle(run_path / "infos.pkl")
    audit = load_json(run_path / "audit_summary.json")
    if len(observations) != len(infos):
        raise ValueError(f"{label}: observations and infos length differ")
    if audit.get("run_status") != "complete":
        raise ValueError(f"{label}: run is not complete")
    cameras = sorted(observations[0]["rgb"])
    if any(sorted(obs[modality]) != cameras for obs in observations for modality in ("rgb", "semantic", "depth")):
        raise ValueError(f"{label}: camera sets differ across frames/modalities")

    rows: list[dict[str, Any]] = []
    previous_distributions: dict[str, np.ndarray] = {}
    for frame_index, (observation, info) in enumerate(zip(observations, infos, strict=True)):
        for camera in cameras:
            metrics = frame_camera_metrics(
                observation["rgb"][camera], observation["semantic"][camera], observation["depth"][camera]
            )
            distribution = semantic_distribution(observation["semantic"][camera])
            previous = previous_distributions.get(camera)
            metrics["semantic_distribution_l1_to_previous"] = (
                None if previous is None else float(np.abs(distribution - previous).sum())
            )
            previous_distributions[camera] = distribution
            rows.append({
                "run_label": label,
                "frame_index": frame_index,
                "timestamp_s": float(info["timestamp"]),
                "camera": camera,
                **metrics,
            })

    first_calibration = calibration_metrics(infos[0], observations[0])
    calibration_stable = True
    for info in infos[1:]:
        for camera in cameras:
            calibration_stable &= bool(np.array_equal(
                np.asarray(info["cam_params"][camera]["v2c"]),
                np.asarray(infos[0]["cam_params"][camera]["v2c"]),
            ))
            calibration_stable &= info["cam_params"][camera]["intrinsic"] == infos[0]["cam_params"][camera]["intrinsic"]

    selected = sorted({0, len(observations) // 2, len(observations) - 1})
    input_manifest = []
    for frame_index in selected:
        for camera in cameras:
            rgb = observations[frame_index]["rgb"][camera]
            input_manifest.append({
                "frame_index": frame_index,
                "timestamp_s": float(infos[frame_index]["timestamp"]),
                "camera": camera,
                "shape": list(rgb.shape),
                "dtype": str(rgb.dtype),
                "rgb_array_sha256": array_sha256(rgb),
            })

    by_camera = {
        camera: aggregate_camera([row for row in rows if row["camera"] == camera])
        for camera in cameras
    }
    temporal = {
        camera: {
            "semantic_distribution_l1_mean": float(np.mean([
                row["semantic_distribution_l1_to_previous"] for row in rows
                if row["camera"] == camera and row["semantic_distribution_l1_to_previous"] is not None
            ])),
            "semantic_distribution_l1_max": float(np.max([
                row["semantic_distribution_l1_to_previous"] for row in rows
                if row["camera"] == camera and row["semantic_distribution_l1_to_previous"] is not None
            ])),
        }
        for camera in cameras
    }
    contract_pass = all(
        item["array_shape_matches_intrinsic"]
        and item["principal_point_in_bounds"]
        and item["positive_fov"]
        and item["rotation_orthonormal_max_error"] < 1e-5
        and abs(item["rotation_determinant"] - 1.0) < 1e-5
        for item in first_calibration.values()
    ) and calibration_stable
    numeric_pass = all(
        row["depth_nonfinite_fraction"] == 0.0
        and row["depth_nonpositive_fraction"] == 0.0
        and row["rgb_dtype"] == "uint8"
        and row["semantic_dtype"] == "uint8"
        and row["depth_dtype"] == "float32"
        for row in rows
    )
    summary = {
        "run_path": str(run_path),
        "observation_count": len(observations),
        "completed_steps": audit["completed_steps"],
        "cameras": cameras,
        "calibration_contract": first_calibration,
        "calibration_constant_across_frames": calibration_stable,
        "array_and_calibration_contract_check": "accepted" if contract_pass else "rejected",
        "numeric_validity_check": "accepted" if numeric_pass else "rejected",
        "camera_summaries": by_camera,
        "temporal_diagnostics": temporal,
        "receiver_input_manifest": input_manifest,
        "cross_modal_interpretation": "down-weighted",
        "claim_boundary": (
            "Supports renderer-internal array, calibration, numerical, and boundary-co-variation diagnostics only; "
            "does not establish real-sensor accuracy, semantic/depth truth, cross-camera 3D consistency, or AD behavior."
        ),
    }
    return summary, rows, observations


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [key for key in rows[0] if key not in {"semantic_fractions", "rgb_sha256"}]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fields})


def semantic_rgb(semantic: np.ndarray) -> np.ndarray:
    clipped = np.clip(semantic, 0, len(SEMANTIC_COLORS) - 1)
    return SEMANTIC_COLORS[clipped]


def make_examples(path: Path, runs: dict[str, list[Any]]) -> None:
    import matplotlib.pyplot as plt
    cameras = ["CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT"]
    fig, axes = plt.subplots(len(runs), 9, figsize=(24, 5 * len(runs)))
    axes = np.atleast_2d(axes)
    for row_index, (label, observations) in enumerate(runs.items()):
        observation = observations[len(observations) // 2]
        for camera_index, camera in enumerate(cameras):
            rgb = observation["rgb"][camera]
            semantic = observation["semantic"][camera]
            depth = observation["depth"][camera]
            panels = (rgb, semantic_rgb(semantic), depth)
            titles = (f"{label} {camera} RGB", "semantic (HUGSIM)", "depth (HUGSIM)")
            for panel_index, (panel, title) in enumerate(zip(panels, titles, strict=True)):
                axis = axes[row_index, camera_index * 3 + panel_index]
                axis.imshow(panel, cmap="magma" if panel_index == 2 else None,
                            vmin=0 if panel_index == 2 else None,
                            vmax=float(np.percentile(depth, 95)) if panel_index == 2 else None)
                axis.set_title(title, fontsize=9)
                axis.axis("off")
    fig.suptitle("Normal-scene receiver arrays and HUGSIM privileged outputs (middle frame)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def make_plot(path: Path, summaries: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt
    labels = list(summaries)
    cameras = summaries[labels[0]]["cameras"]
    x = np.arange(len(cameras))
    width = 0.8 / len(labels)
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    for label_index, label in enumerate(labels):
        offset = (label_index - (len(labels) - 1) / 2) * width
        cams = summaries[label]["camera_summaries"]
        axes[0, 0].bar(x + offset, [cams[c]["semantic_edges_near_depth_edge_fraction"]["mean"] for c in cameras], width, label=label)
        axes[0, 1].bar(x + offset, [cams[c]["rgb_semantic_boundary_gradient_ratio"]["mean"] for c in cameras], width, label=label)
        axes[1, 0].bar(x + offset, [summaries[label]["temporal_diagnostics"][c]["semantic_distribution_l1_max"] for c in cameras], width, label=label)
        front_rows = [r for r in rows if r["run_label"] == label and r["camera"] == "CAM_FRONT"]
        axes[1, 1].plot([r["timestamp_s"] for r in front_rows], [r["depth_median_m"] for r in front_rows], label=label)
    axes[0, 0].set_title("Semantic boundaries near depth discontinuity")
    axes[0, 0].set_ylim(0, 1)
    axes[0, 1].set_title("RGB gradient ratio: semantic boundary / interior")
    axes[1, 0].set_title("Max frame-to-frame semantic distribution L1")
    axes[1, 1].set_title("CAM_FRONT median HUGSIM depth over time")
    axes[1, 1].set_xlabel("time (s)")
    for axis in axes.flat[:3]:
        axis.set_xticks(x, cameras, rotation=30, ha="right")
    for axis in axes.flat:
        axis.grid(alpha=0.25)
        axis.legend()
    fig.suptitle("HUGSIM normal-scene internal sensor diagnostics (not real-sensor accuracy)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    runs = parse_runs(args.run)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    summaries: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    observations_by_run: dict[str, list[Any]] = {}
    for label, run_path in runs.items():
        summary, rows, observations = analyze_run(label, run_path)
        summaries[label] = summary
        all_rows.extend(rows)
        observations_by_run[label] = observations
    result = {
        "audit_id": "hugsim_normal_scene_sensor_audit_001",
        "status": "complete",
        "runs": summaries,
        "evidence_decisions": {
            "array_calibration_contract": (
                "accepted" if all(s["array_and_calibration_contract_check"] == "accepted" for s in summaries.values()) else "rejected"
            ),
            "numeric_validity": (
                "accepted" if all(s["numeric_validity_check"] == "accepted" for s in summaries.values()) else "rejected"
            ),
            "rgb_semantic_depth_internal_covariation": "down-weighted",
            "real_sensor_or_cross_camera_3d_consistency": "rejected",
        },
        "rejection_basis": (
            "not_tested: no independent real RGB/labels/depth and no cross-camera correspondence reference; "
            "the rejected label applies to those stronger claims, not to HUGSIM capability failure."
        ),
    }
    json_path = output / "normal_scene_sensor_audit.json"
    csv_path = output / "normal_scene_sensor_timeseries.csv"
    plot_path = output / "normal_scene_sensor_diagnostics.png"
    examples_path = output / "normal_scene_receiver_arrays.png"
    write_csv(csv_path, all_rows)
    make_plot(plot_path, summaries, all_rows)
    make_examples(examples_path, observations_by_run)
    result["artifacts"] = {
        "json": str(json_path), "timeseries_csv": str(csv_path),
        "diagnostic_plot": str(plot_path), "receiver_array_examples": str(examples_path),
    }
    json_path.write_text(json.dumps(jsonable(result), indent=2), encoding="utf-8")
    print(json.dumps(jsonable(result["evidence_decisions"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
