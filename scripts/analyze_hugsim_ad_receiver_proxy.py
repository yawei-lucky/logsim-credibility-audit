#!/usr/bin/env python3
"""Analyze HUGSIM counterfactuals with a frozen task-receiver proxy.

The receiver here is intentionally modest: it uses the front camera's rendered
semantic/depth outputs to approximate task variables a camera-only AD receiver
would need, such as visible vehicle area, center-lane overlap, depth, and
temporal stability. It is not an AD model and must not be reported as an
AD-agent response.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-hugsim-ad-receiver-proxy")

CAR_SEMANTIC_ID = 13
MIN_COMPONENT_PIXELS = 250


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze HUGSIM receiver-proxy causal response."
    )
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run spec in the form label=/path/to/run.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--camera", default="CAM_FRONT")
    parser.add_argument("--car-semantic-id", type=int, default=CAR_SEMANTIC_ID)
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


def connected_components(mask: np.ndarray) -> list[np.ndarray]:
    if not mask.any():
        return []
    try:
        import cv2  # type: ignore

        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8),
            8,
        )
        components = []
        for index in range(1, count):
            if int(stats[index, cv2.CC_STAT_AREA]) >= MIN_COMPONENT_PIXELS:
                components.append(labels == index)
        return components
    except Exception:
        return [mask]


def component_feature(
    component: np.ndarray,
    depth: np.ndarray,
    image_shape: tuple[int, int],
) -> dict[str, float]:
    height, width = image_shape
    ys, xs = np.nonzero(component)
    x1 = int(xs.min())
    x2 = int(xs.max()) + 1
    y1 = int(ys.min())
    y2 = int(ys.max()) + 1
    area = int(component.sum())
    center_left = int(width * 0.42)
    center_right = int(width * 0.58)
    overlap_left = max(x1, center_left)
    overlap_right = min(x2, center_right)
    center_overlap_px = max(0, overlap_right - overlap_left) * (y2 - y1)
    bbox_area = max(1, (x2 - x1) * (y2 - y1))
    component_depth = depth[component]
    median_depth = float(np.nanmedian(component_depth))
    min_depth = float(np.nanmin(component_depth))
    area_fraction = float(area / (height * width))
    bbox_area_fraction = float(bbox_area / (height * width))
    center_overlap_fraction = float(center_overlap_px / bbox_area)
    bottom_fraction = float(y2 / height)
    depth_score = float(1.0 / max(median_depth, 0.25))
    hazard_proxy = float(
        100.0 * area_fraction
        + 2.0 * center_overlap_fraction
        + 1.5 * bottom_fraction
        + 4.0 * depth_score
    )
    return {
        "area_px": float(area),
        "area_fraction": area_fraction,
        "bbox_area_fraction": bbox_area_fraction,
        "bbox_x1": float(x1),
        "bbox_y1": float(y1),
        "bbox_x2": float(x2),
        "bbox_y2": float(y2),
        "center_overlap_fraction": center_overlap_fraction,
        "median_depth_m": median_depth,
        "min_depth_m": min_depth,
        "bottom_fraction": bottom_fraction,
        "hazard_proxy": hazard_proxy,
    }


def receiver_features(
    observation: dict[str, Any],
    camera: str,
    car_semantic_id: int,
) -> dict[str, Any]:
    semantic = np.asarray(observation["semantic"][camera])
    if semantic.ndim == 3:
        semantic = semantic[..., 0]
    depth = np.asarray(observation["depth"][camera], dtype=np.float64)
    mask = semantic == car_semantic_id
    height, width = mask.shape
    components = [
        component_feature(component, depth, (height, width))
        for component in connected_components(mask)
    ]
    components.sort(key=lambda item: item["hazard_proxy"], reverse=True)
    if components:
        top = components[0]
        visible_area_fraction = float(sum(item["area_fraction"] for item in components))
        center_area_fraction = float(
            sum(
                item["area_fraction"] * item["center_overlap_fraction"]
                for item in components
            )
        )
        return {
            "vehicle_component_count": len(components),
            "visible_vehicle_area_fraction": visible_area_fraction,
            "center_vehicle_area_fraction": center_area_fraction,
            "top_hazard_proxy": top["hazard_proxy"],
            "top_center_overlap_fraction": top["center_overlap_fraction"],
            "top_median_depth_m": top["median_depth_m"],
            "top_min_depth_m": top["min_depth_m"],
            "top_bbox_area_fraction": top["bbox_area_fraction"],
            "top_bottom_fraction": top["bottom_fraction"],
            "components": components,
        }
    return {
        "vehicle_component_count": 0,
        "visible_vehicle_area_fraction": 0.0,
        "center_vehicle_area_fraction": 0.0,
        "top_hazard_proxy": 0.0,
        "top_center_overlap_fraction": 0.0,
        "top_median_depth_m": None,
        "top_min_depth_m": None,
        "top_bbox_area_fraction": 0.0,
        "top_bottom_fraction": 0.0,
        "components": [],
    }


def state_reference(info: dict[str, Any]) -> dict[str, Any]:
    ego = np.asarray(info["ego_box"], dtype=np.float64)
    actors = [np.asarray(box, dtype=np.float64) for box in info.get("obj_boxes", [])]
    refs = []
    for index, actor in enumerate(actors):
        longitudinal_m = float(actor[0] - ego[0])
        lateral_m = float(actor[1] - ego[1])
        refs.append(
            {
                "actor_index": index,
                "longitudinal_m": longitudinal_m,
                "lateral_m": lateral_m,
                "same_lane_proxy": bool(abs(lateral_m) <= 1.75),
                "front_proxy": bool(longitudinal_m > 0.0),
            }
        )
    front_actors = [
        ref for ref in refs if ref["front_proxy"] and ref["same_lane_proxy"]
    ]
    nearest_same_lane = (
        min(front_actors, key=lambda item: item["longitudinal_m"])
        if front_actors
        else None
    )
    return {
        "actors": refs,
        "nearest_same_lane_front_actor": nearest_same_lane,
        "same_lane_front_actor_count": len(front_actors),
    }


def summarize_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    visible_rows = [
        row for row in rows if row["visible_vehicle_area_fraction"] > 0.0005
    ]
    depth_values = [
        float(row["top_median_depth_m"])
        for row in rows
        if row["top_median_depth_m"] is not None
    ]
    hazard_values = [float(row["top_hazard_proxy"]) for row in rows]
    area_values = [float(row["visible_vehicle_area_fraction"]) for row in rows]
    center_values = [float(row["center_vehicle_area_fraction"]) for row in rows]
    counts = [int(row["vehicle_component_count"]) for row in rows]
    active_hazard = [float(row["top_hazard_proxy"]) for row in visible_rows]
    return {
        "frame_count": len(rows),
        "visible_frame_count": len(visible_rows),
        "first_visible_s": (
            float(visible_rows[0]["timestamp_s"]) if visible_rows else None
        ),
        "peak_hazard_proxy": float(max(hazard_values)) if hazard_values else 0.0,
        "mean_active_hazard_proxy": (
            float(np.mean(active_hazard)) if active_hazard else 0.0
        ),
        "peak_visible_area_fraction": float(max(area_values)) if area_values else 0.0,
        "peak_center_vehicle_area_fraction": (
            float(max(center_values)) if center_values else 0.0
        ),
        "minimum_top_median_depth_m": (
            float(min(depth_values)) if depth_values else None
        ),
        "maximum_vehicle_component_count": int(max(counts)) if counts else 0,
        "tracking_presence_stability": (
            float(len(visible_rows) / len(rows)) if rows else 0.0
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
                "id": "distance_response_front_near_vs_far",
                "expected": "closer same-lane vehicle should increase receiver hazard proxy and reduce estimated depth",
                "observed": {
                    "front_far_peak_hazard": far["peak_hazard_proxy"],
                    "front_near_peak_hazard": near["peak_hazard_proxy"],
                    "front_far_min_depth_m": far["minimum_top_median_depth_m"],
                    "front_near_min_depth_m": near["minimum_top_median_depth_m"],
                },
                "decision": (
                    "accepted"
                    if near["peak_hazard_proxy"] > far["peak_hazard_proxy"]
                    and near["minimum_top_median_depth_m"] is not None
                    and far["minimum_top_median_depth_m"] is not None
                    and near["minimum_top_median_depth_m"]
                    < far["minimum_top_median_depth_m"]
                    else "rejected"
                ),
            }
        )

    if has("front_near", "adjacent_near"):
        front = summaries["front_near"]
        adjacent = summaries["adjacent_near"]
        checks.append(
            {
                "id": "lane_relation_response_front_vs_adjacent",
                "expected": "same-lane near vehicle should outrank adjacent-lane near vehicle for a front-path hazard proxy",
                "observed": {
                    "front_near_peak_hazard": front["peak_hazard_proxy"],
                    "adjacent_near_peak_hazard": adjacent["peak_hazard_proxy"],
                    "front_near_peak_center_area": front[
                        "peak_center_vehicle_area_fraction"
                    ],
                    "adjacent_near_peak_center_area": adjacent[
                        "peak_center_vehicle_area_fraction"
                    ],
                },
                "decision": (
                    "accepted"
                    if front["peak_hazard_proxy"] > adjacent["peak_hazard_proxy"]
                    and front["peak_center_vehicle_area_fraction"]
                    >= adjacent["peak_center_vehicle_area_fraction"]
                    else "down-weighted"
                ),
            }
        )

    if has("front_far", "multicar_merge"):
        far = summaries["front_far"]
        merge = summaries["multicar_merge"]
        checks.append(
            {
                "id": "multicar_merge_prominence",
                "expected": "multi-car merge should produce stronger visible vehicle and center-path evidence than the far-front control",
                "observed": {
                    "front_far_peak_hazard": far["peak_hazard_proxy"],
                    "multicar_merge_peak_hazard": merge["peak_hazard_proxy"],
                    "front_far_max_components": far["maximum_vehicle_component_count"],
                    "multicar_merge_max_components": merge[
                        "maximum_vehicle_component_count"
                    ],
                },
                "decision": (
                    "accepted"
                    if merge["peak_hazard_proxy"] > far["peak_hazard_proxy"]
                    and merge["maximum_vehicle_component_count"]
                    >= far["maximum_vehicle_component_count"]
                    else "down-weighted"
                ),
            }
        )

    return checks


def write_csv(path: Path, rows_by_run: dict[str, list[dict[str, Any]]]) -> None:
    fieldnames = [
        "run_label",
        "frame_index",
        "timestamp_s",
        "vehicle_component_count",
        "visible_vehicle_area_fraction",
        "center_vehicle_area_fraction",
        "top_hazard_proxy",
        "top_center_overlap_fraction",
        "top_median_depth_m",
        "top_min_depth_m",
        "top_bbox_area_fraction",
        "top_bottom_fraction",
        "same_lane_front_actor_count",
        "nearest_same_lane_front_actor_index",
        "nearest_same_lane_front_actor_longitudinal_m",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for label, rows in rows_by_run.items():
            for row in rows:
                nearest = row["state_reference"]["nearest_same_lane_front_actor"]
                writer.writerow(
                    {
                        "run_label": label,
                        "frame_index": row["frame_index"],
                        "timestamp_s": row["timestamp_s"],
                        "vehicle_component_count": row[
                            "vehicle_component_count"
                        ],
                        "visible_vehicle_area_fraction": row[
                            "visible_vehicle_area_fraction"
                        ],
                        "center_vehicle_area_fraction": row[
                            "center_vehicle_area_fraction"
                        ],
                        "top_hazard_proxy": row["top_hazard_proxy"],
                        "top_center_overlap_fraction": row[
                            "top_center_overlap_fraction"
                        ],
                        "top_median_depth_m": row["top_median_depth_m"],
                        "top_min_depth_m": row["top_min_depth_m"],
                        "top_bbox_area_fraction": row["top_bbox_area_fraction"],
                        "top_bottom_fraction": row["top_bottom_fraction"],
                        "same_lane_front_actor_count": row["state_reference"][
                            "same_lane_front_actor_count"
                        ],
                        "nearest_same_lane_front_actor_index": (
                            nearest["actor_index"] if nearest else None
                        ),
                        "nearest_same_lane_front_actor_longitudinal_m": (
                            nearest["longitudinal_m"] if nearest else None
                        ),
                    }
                )


def make_response_plot(
    path: Path,
    rows_by_run: dict[str, list[dict[str, Any]]],
    summaries: dict[str, dict[str, Any]],
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
            [row["top_hazard_proxy"] for row in rows],
            label=label,
            linewidth=2,
            color=color,
        )
        axes[0, 1].plot(
            times,
            [row["visible_vehicle_area_fraction"] for row in rows],
            label=label,
            linewidth=2,
            color=color,
        )
        axes[1, 0].plot(
            times,
            [row["center_vehicle_area_fraction"] for row in rows],
            label=label,
            linewidth=2,
            color=color,
        )
        axes[1, 1].plot(
            times,
            [
                np.nan
                if row["top_median_depth_m"] is None
                else row["top_median_depth_m"]
                for row in rows
            ],
            label=label,
            linewidth=2,
            color=color,
        )

    axes[0, 0].set_title("Frozen task receiver proxy: hazard")
    axes[0, 0].set_ylabel("hazard proxy")
    axes[0, 1].set_title("Visible vehicle evidence")
    axes[0, 1].set_ylabel("semantic vehicle area fraction")
    axes[1, 0].set_title("Center-path evidence")
    axes[1, 0].set_ylabel("center vehicle area fraction")
    axes[1, 1].set_title("Top component depth")
    axes[1, 1].set_ylabel("median depth (m)")
    axes[1, 1].invert_yaxis()
    for axis in axes.ravel():
        axis.set_xlabel("simulation time (s)")
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    figure.suptitle(
        "HUGSIM AD-receiver-proxy causal response across large interventions",
        fontsize=15,
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)


def label_image(image: np.ndarray, label: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    band_height = 32
    canvas = np.zeros(
        (image.shape[0] + band_height, image.shape[1], 3),
        dtype=np.uint8,
    )
    canvas[band_height:] = image
    pil_image = Image.fromarray(canvas)
    ImageDraw.Draw(pil_image).text((8, 8), label, fill=(255, 255, 255))
    return np.asarray(pil_image)


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
    frame_indices = sorted({0, frame_count // 3, (2 * frame_count) // 3, frame_count - 1})
    figure, axes = plt.subplots(
        len(frame_indices),
        len(labels),
        figsize=(4.0 * len(labels), 2.7 * len(frame_indices)),
        constrained_layout=True,
    )
    if len(frame_indices) == 1:
        axes = axes[np.newaxis, :]
    if len(labels) == 1:
        axes = axes[:, np.newaxis]

    for row_index, frame_index in enumerate(frame_indices):
        for col_index, label in enumerate(labels):
            rgb = observations_by_run[label][frame_index]["rgb"][camera]
            metric = rows_by_run[label][frame_index]
            axes[row_index, col_index].imshow(rgb)
            axes[row_index, col_index].set_xticks([])
            axes[row_index, col_index].set_yticks([])
            axes[row_index, col_index].set_title(
                f"{label}\nt={metric['timestamp_s']:.2f}s H={metric['top_hazard_proxy']:.2f}",
                fontsize=9,
            )
    figure.suptitle("Front-camera inputs seen by the receiver proxy", fontsize=14)
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
        tiles = []
        for label in labels:
            rgb = observations_by_run[label][frame_index]["rgb"][camera]
            hazard = rows_by_run[label][frame_index]["top_hazard_proxy"]
            timestamp = rows_by_run[label][frame_index]["timestamp_s"]
            tiles.append(label_image(rgb, f"{label}  t={timestamp:.2f}s  H={hazard:.2f}"))
        frames.append(np.concatenate(tiles, axis=1))
    ImageSequenceClip(frames, fps=4).write_videofile(str(path), logger=None)


def main() -> int:
    args = parse_args()
    runs = parse_run_specs(args.run)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

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

        rows = []
        for frame_index, (observation, info) in enumerate(
            zip(observations, infos, strict=True)
        ):
            features = receiver_features(
                observation,
                args.camera,
                args.car_semantic_id,
            )
            features.update(
                {
                    "frame_index": frame_index,
                    "timestamp_s": float(info["timestamp"]),
                    "state_reference": state_reference(info),
                }
            )
            rows.append(features)
        observations_by_run[label] = observations
        rows_by_run[label] = rows
        summaries[label] = summarize_series(rows)
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

    csv_path = output / "ad_receiver_proxy_timeseries.csv"
    plot_path = output / "ad_receiver_proxy_response.png"
    contact_sheet_path = output / "ad_receiver_proxy_front_contact_sheet.png"
    video_path = output / "ad_receiver_proxy_front_grid.mp4"
    write_csv(csv_path, rows_by_run)
    make_response_plot(plot_path, rows_by_run, summaries)
    make_contact_sheet(contact_sheet_path, observations_by_run, rows_by_run, args.camera)
    make_grid_video(video_path, observations_by_run, rows_by_run, args.camera)

    checks = causal_checks(summaries)
    summary = {
        "receiver_contract": {
            "name": "simulator_internal_task_receiver_proxy_v0",
            "input": {
                "camera": args.camera,
                "modalities": ["semantic", "depth"],
                "car_semantic_id": args.car_semantic_id,
            },
            "status": "not_an_ad_agent",
            "scope": (
                "Measures task-relevant visibility, center-path occupancy, "
                "depth, and a fixed hazard proxy from HUGSIM outputs. It is "
                "useful for causal-response screening but cannot establish "
                "real AD model behavior or real-sensor consistency."
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
    with (output / "ad_receiver_proxy_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(jsonable(summary), stream, indent=2)
    print(json.dumps(jsonable(summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
