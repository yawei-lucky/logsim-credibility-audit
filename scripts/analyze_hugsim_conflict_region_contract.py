#!/usr/bin/env python3
"""Freeze and exercise a local swept-corridor conflict-region contract."""

from __future__ import annotations

import argparse
import json
import math
import pickle
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import LineString, Polygon, mapping

from make_hugsim_actor_placement_metadata import heading_vector, reference_model_path
from render_hugsim_exact_source_pose import select_camera_records, sha256_file


def oriented_footprint(
    centre_xz: np.ndarray, heading_from_x_rad: float, width_m: float, length_m: float
) -> Polygon:
    if width_m <= 0.0 or length_m <= 0.0:
        raise ValueError("footprint dimensions must be positive")
    forward = np.asarray(
        [math.cos(heading_from_x_rad), math.sin(heading_from_x_rad)], dtype=float
    )
    left = np.asarray([-forward[1], forward[0]], dtype=float)
    centre = np.asarray(centre_xz, dtype=float)
    corners = [
        centre + forward * length_m / 2 + left * width_m / 2,
        centre + forward * length_m / 2 - left * width_m / 2,
        centre - forward * length_m / 2 - left * width_m / 2,
        centre - forward * length_m / 2 + left * width_m / 2,
    ]
    return Polygon(corners)


def classify_boolean_occupancy(
    timestamps: np.ndarray,
    occupied: np.ndarray,
    *,
    spatial_avoidance_known: bool = False,
    enters_after_horizon_known: bool = False,
) -> dict[str, Any]:
    times = np.asarray(timestamps, dtype=float)
    flags = np.asarray(occupied, dtype=bool)
    if times.ndim != 1 or flags.shape != times.shape or len(times) < 2:
        raise ValueError("occupancy requires aligned one-dimensional samples")
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0.0):
        raise ValueError("occupancy timestamps must be finite and increasing")
    if not np.any(flags):
        if spatial_avoidance_known and enters_after_horizon_known:
            raise ValueError("avoidance and after-horizon cannot both be asserted")
        category = (
            "spatial_avoidance"
            if spatial_avoidance_known
            else "after_horizon"
            if enters_after_horizon_known
            else "no_occupancy_unresolved"
        )
        return {"category": category, "interval": None, "finite_c_eligible": False}

    starts = np.flatnonzero(flags & np.r_[True, ~flags[:-1]])
    ends = np.flatnonzero(flags & np.r_[~flags[1:], True])
    intervals = [[float(times[start]), float(times[end])] for start, end in zip(starts, ends, strict=True)]
    if flags[0] or flags[-1]:
        sides = []
        if flags[0]:
            sides.append("left")
        if flags[-1]:
            sides.append("right")
        return {
            "category": "censored_" + "_and_".join(sides),
            "interval": None,
            "observed_intervals": intervals,
            "finite_c_eligible": False,
        }
    if len(intervals) != 1:
        return {
            "category": "multiple_intervals",
            "interval": None,
            "observed_intervals": intervals,
            "finite_c_eligible": False,
        }
    return {
        "category": "single_complete_interval",
        "interval": intervals[0],
        "finite_c_eligible": True,
    }


def signed_occupancy_gap(
    ego_occupancy: dict[str, Any], actor_occupancy: dict[str, Any]
) -> float | None:
    if not ego_occupancy["finite_c_eligible"] or not actor_occupancy["finite_c_eligible"]:
        return None
    ego_in, ego_out = ego_occupancy["interval"]
    actor_in, actor_out = actor_occupancy["interval"]
    return float(max(ego_in, actor_in) - min(ego_out, actor_out))


def interpolate_path(
    source_times: np.ndarray, source_points: np.ndarray, sample_times: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    times = np.asarray(source_times, dtype=float)
    points = np.asarray(source_points, dtype=float)
    samples = np.asarray(sample_times, dtype=float)
    if points.shape != (len(times), 2) or len(times) < 3:
        raise ValueError("path must contain at least three aligned x-z samples")
    dense = np.column_stack(
        [np.interp(samples, times, points[:, axis]) for axis in range(2)]
    )
    derivative = np.gradient(dense, samples, axis=0)
    speed = np.linalg.norm(derivative, axis=1)
    if np.any(speed < 1e-6):
        raise ValueError("interpolated path has undefined heading")
    headings = np.arctan2(derivative[:, 1], derivative[:, 0])
    return dense, headings


def local_conflict_region(
    ego_points: np.ndarray,
    conflict_xz: np.ndarray,
    actor_heading_deg: float,
    ego_width_m: float,
    actor_width_m: float,
    local_half_length_m: float,
) -> Polygon:
    points = np.asarray(ego_points, dtype=float)
    conflict = np.asarray(conflict_xz, dtype=float)
    inside = np.flatnonzero(np.linalg.norm(points - conflict, axis=1) <= local_half_length_m)
    if len(inside) < 2:
        raise ValueError("ego path does not sufficiently cover local conflict region")
    start = max(0, int(inside[0]) - 1)
    end = min(len(points), int(inside[-1]) + 2)
    ego_corridor = LineString(points[start:end]).buffer(
        ego_width_m / 2, cap_style=2, join_style=2
    )
    forward = heading_vector(actor_heading_deg)
    actor_line = LineString(
        [conflict - local_half_length_m * forward, conflict + local_half_length_m * forward]
    )
    actor_corridor = actor_line.buffer(actor_width_m / 2, cap_style=2, join_style=2)
    region = ego_corridor.intersection(actor_corridor)
    if region.is_empty or region.geom_type != "Polygon":
        raise ValueError(f"conflict corridor intersection is {region.geom_type} or empty")
    return region


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--dynamic-manifest", type=Path, required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--calibration-reference-run", type=Path, required=True)
    parser.add_argument("--ego-width-m", type=float, default=1.6)
    parser.add_argument("--ego-length-m", type=float, default=3.0)
    parser.add_argument("--local-half-length-m", type=float, default=12.0)
    parser.add_argument("--sample-dt-s", type=float, default=0.01)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_metadata_path = args.source_metadata.expanduser().resolve()
    dynamic_manifest_path = args.dynamic_manifest.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (source_metadata_path, dynamic_manifest_path, calibration_run / "infos.pkl"):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    if args.sample_dt_s <= 0.0 or args.local_half_length_m <= 0.0:
        raise ValueError("sampling interval and local half length must be positive")

    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
    dynamic_manifest = json.loads(dynamic_manifest_path.read_text(encoding="utf-8"))
    if args.condition not in dynamic_manifest["conditions"]:
        raise ValueError("unknown dynamic condition")
    condition = dynamic_manifest["conditions"][args.condition]
    dynamic_metadata_path = Path(condition["metadata"])
    dynamic_metadata = json.loads(dynamic_metadata_path.read_text(encoding="utf-8"))
    with (calibration_run / "infos.pkl").open("rb") as stream:
        infos = pickle.load(stream)
    front_l2c = np.asarray(
        infos[0]["cam_params"]["CAM_FRONT"]["l2c"], dtype=np.float64
    )

    reference = reference_model_path(source_metadata, front_l2c)
    reference_times = np.asarray([row["timestamp_s"] for row in reference])
    reference_points = np.asarray(
        [[row["world_x_m"], row["world_z_m"]] for row in reference]
    )
    actor_spec = dynamic_manifest["actor"]
    actor_width, actor_length, _ = (
        float(value) for value in actor_spec["dimensions_wlh_m"]
    )
    corridor = actor_spec["corridor"]
    conflict_xz = np.asarray(corridor["conflict_centre_world_xz_m"], dtype=float)
    region = local_conflict_region(
        reference_points,
        conflict_xz,
        float(corridor["heading_deg_from_world_positive_z"]),
        args.ego_width_m,
        actor_width,
        args.local_half_length_m,
    )

    frame_indices = [int(value) for value in dynamic_manifest["frame_indices"]]
    frame_times = np.asarray(
        [float(dynamic_manifest["timestamps_s"][str(index)]) for index in frame_indices]
    )
    sample_times = np.arange(
        frame_times[0], frame_times[-1] + args.sample_dt_s * 0.5, args.sample_dt_s
    )
    sample_times = sample_times[sample_times <= frame_times[-1] + 1e-12]
    ego_points, ego_headings = interpolate_path(
        reference_times, reference_points, sample_times
    )

    actor_id = actor_spec["id"]
    actor_points = []
    for frame_index in frame_indices:
        records = select_camera_records(dynamic_metadata, frame_index)
        transform = np.asarray(records["CAM_FRONT"]["dynamics"][actor_id], dtype=float)
        actor_points.append(transform[[0, 2], 3])
    actor_points = np.asarray(actor_points)
    dense_actor_points, actor_headings = interpolate_path(
        frame_times, actor_points, sample_times
    )

    ego_occupied = np.asarray(
        [
            oriented_footprint(point, heading, args.ego_width_m, args.ego_length_m).intersects(region)
            for point, heading in zip(ego_points, ego_headings, strict=True)
        ]
    )
    actor_occupied = np.asarray(
        [
            oriented_footprint(point, heading, actor_width, actor_length).intersects(region)
            for point, heading in zip(dense_actor_points, actor_headings, strict=True)
        ]
    )
    ego_occupancy = classify_boolean_occupancy(sample_times, ego_occupied)
    actor_occupancy = classify_boolean_occupancy(sample_times, actor_occupied)
    gap = signed_occupancy_gap(ego_occupancy, actor_occupancy)
    finite_eligible = gap is not None

    output.mkdir(parents=True)
    geojson_path = output / "conflict_region.geojson"
    geojson_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"name": "C", "units": "world x-z metres"},
                "geometry": mapping(region),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(9, 6.5), constrained_layout=True)
    region_x, region_z = region.exterior.xy
    axis.fill(region_x, region_z, color="#ef8a62", alpha=0.45, label="Conflict region C")
    axis.plot(reference_points[:, 0], reference_points[:, 1], color="#2166ac", linewidth=2, label="Released ego reference path")
    axis.plot(actor_points[:, 0], actor_points[:, 1], color="#1b7837", linewidth=2, label="Scripted actor path")
    axis.scatter(*conflict_xz, marker="x", s=90, linewidths=2.5, color="black", label="Declared conflict centre")
    for label, occupancy, points, color in (
        ("ego", ego_occupancy, ego_points, "#2166ac"),
        ("actor", actor_occupancy, dense_actor_points, "#1b7837"),
    ):
        if occupancy["finite_c_eligible"]:
            for boundary_time in occupancy["interval"]:
                index = int(np.argmin(np.abs(sample_times - boundary_time)))
                axis.scatter(points[index, 0], points[index, 1], s=45, color=color, edgecolor="white", zorder=5)
                axis.annotate(
                    f"{label} {boundary_time:.2f}s",
                    points[index],
                    xytext=(5, 6),
                    textcoords="offset points",
                    fontsize=8,
                )
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("world x (m)")
    axis.set_ylabel("world z (m)")
    axis.set_title(
        "scene-0041 opposing-path occupancy contract\n"
        "C is a local buffered-centreline intersection, not a safety boundary"
    )
    axis.grid(alpha=0.25)
    axis.legend(loc="best", fontsize=8)
    plot_path = output / "conflict_region_contract.png"
    figure.savefig(plot_path, dpi=180)
    plt.close(figure)

    result = {
        "audit_id": "hugsim_conflict_region_contract_001",
        "date": date.today().isoformat(),
        "condition": args.condition,
        "inputs": {
            "source_metadata": str(source_metadata_path),
            "source_metadata_sha256": sha256_file(source_metadata_path),
            "dynamic_manifest": str(dynamic_manifest_path),
            "dynamic_manifest_sha256": sha256_file(dynamic_manifest_path),
            "dynamic_metadata": str(dynamic_metadata_path),
            "dynamic_metadata_sha256": sha256_file(dynamic_metadata_path),
            "calibration_infos": str(calibration_run / "infos.pkl"),
            "calibration_infos_sha256": sha256_file(calibration_run / "infos.pkl"),
        },
        "conflict_region": {
            "definition": "intersection of local ego and actor centreline buffers",
            "conflict_centre_world_xz_m": conflict_xz.tolist(),
            "local_half_length_m": args.local_half_length_m,
            "area_m2": float(region.area),
            "bounds_world_xz_m": [float(value) for value in region.bounds],
            "polygon_geojson": str(geojson_path),
            "polygon_geojson_sha256": sha256_file(geojson_path),
            "visualization": str(plot_path),
            "visualization_sha256": sha256_file(plot_path),
        },
        "footprints": {
            "ego_width_length_m": [args.ego_width_m, args.ego_length_m],
            "ego_source": "HUGSIM HUGSimEnv.whl internal default; not independently measured",
            "actor_width_length_m": [actor_width, actor_length],
            "actor_source": "pinned RealCar wlh.json",
        },
        "motion_and_yaw": {
            "centre_interpolation": "piecewise linear on released metadata timestamps",
            "yaw": "atan2 of the interpolated centreline tangent in world x-z",
            "sampling_dt_s": args.sample_dt_s,
            "maximum_released_timestamp_step_s": float(np.max(np.diff(frame_times))),
            "finite_c_numerical_error_bound_s": 2.0 * args.sample_dt_s,
            "real_motion_model_error": "unqualified",
        },
        "special_branches": {
            "spatial_avoidance": "return category and c=null after full plan path is confirmed disjoint from C",
            "after_horizon": "return category and c=null only when an explicit longer future first enters after the analysis horizon",
            "multiple_entries": "return multiple_intervals and c=null",
            "window_censoring": "return censored_left/right and c=null",
            "unresolved_empty": "return no_occupancy_unresolved and c=null",
        },
        "ego_occupancy": ego_occupancy,
        "actor_occupancy": actor_occupancy,
        "signed_occupancy_gap_s": gap,
        "finite_c_eligible": finite_eligible,
        "overall_passed": finite_eligible,
        "claim_boundary": (
            "A pass qualifies one internally defined geometric occupancy calculation. "
            "The footprint sizes, reconstructed path and actor state are simulator-side; "
            "c=0 is not a real-world safety threshold."
        ),
    }
    result_path = output / "conflict_region_contract.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0 if finite_eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
