#!/usr/bin/env python3
"""Create render-only metadata variants for an excluded actor placement setup."""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from make_hugsim_lead_counterfactual_metadata import (
    add_actor,
    lead_transform,
    model_to_world,
)
from render_hugsim_exact_source_pose import (
    select_camera_records,
    sha256_file,
)


def parse_candidate_specs(specs: list[str]) -> dict[str, tuple[float, float, float]]:
    """Parse ``LABEL=WORLD_X,WORLD_Z,HEADING_DEG`` placement candidates."""

    parsed: dict[str, tuple[float, float, float]] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(
                "--candidate must use LABEL=WORLD_X,WORLD_Z,HEADING_DEG"
            )
        label, raw_values = spec.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or label in parsed:
            raise ValueError(f"invalid or duplicate candidate label: {label!r}")
        parts = raw_values.split(",")
        if len(parts) != 3:
            raise ValueError(
                "--candidate must use LABEL=WORLD_X,WORLD_Z,HEADING_DEG"
            )
        values = tuple(float(value) for value in parts)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("candidate coordinates and heading must be finite")
        parsed[label] = values
    if not parsed:
        raise ValueError("at least one --candidate is required")
    return parsed


def heading_vector(heading_deg: float) -> np.ndarray:
    """Return world ``[x,z]`` forward direction; zero degrees is world +z."""

    radians = math.radians(heading_deg)
    return np.asarray([math.sin(radians), math.cos(radians)], dtype=np.float64)


def candidate_transform(
    world_x: float,
    world_z: float,
    heading_deg: float,
    camera_poses: np.ndarray,
    camera_height: float,
    actor_height_offset_m: float,
) -> np.ndarray:
    return lead_transform(
        np.asarray([world_x, world_z], dtype=np.float64),
        heading_vector(heading_deg),
        camera_poses,
        camera_height,
        actor_height_offset_m,
    )


def reference_model_path(
    metadata: dict[str, Any],
    front_l2c: np.ndarray,
) -> list[dict[str, float]]:
    frame_indices = sorted(
        {
            int(Path(frame["rgb_path"]).stem)
            for frame in metadata.get("frames", [])
            if Path(frame["rgb_path"]).parent.name == "CAM_FRONT"
        }
    )
    rows = []
    for frame_index in frame_indices:
        records = select_camera_records(metadata, frame_index)
        pose = model_to_world(metadata, frame_index, front_l2c)
        rows.append(
            {
                "frame_index": frame_index,
                "timestamp_s": float(records["CAM_FRONT"]["timestamp"]),
                "world_x_m": float(pose[0, 3]),
                "world_z_m": float(pose[2, 3]),
            }
        )
    return rows


def nearest_path_relation(
    path: list[dict[str, float]],
    world_x: float,
    world_z: float,
    actor_heading_deg: float,
) -> dict[str, float | int]:
    if len(path) < 3:
        raise ValueError("reference path requires at least three poses")
    points = np.asarray(
        [[row["world_x_m"], row["world_z_m"]] for row in path],
        dtype=np.float64,
    )
    target = np.asarray([world_x, world_z], dtype=np.float64)
    index = int(np.argmin(np.linalg.norm(points - target, axis=1)))
    before = max(index - 1, 0)
    after = min(index + 1, len(path) - 1)
    tangent = points[after] - points[before]
    if float(np.linalg.norm(tangent)) < 1e-9:
        raise ValueError("nearest reference path tangent is degenerate")
    ego_heading_deg = math.degrees(math.atan2(tangent[0], tangent[1]))
    signed_delta = (actor_heading_deg - ego_heading_deg + 180.0) % 360.0 - 180.0
    return {
        "nearest_frame_index": int(path[index]["frame_index"]),
        "nearest_timestamp_s": float(path[index]["timestamp_s"]),
        "nearest_world_x_m": float(points[index, 0]),
        "nearest_world_z_m": float(points[index, 1]),
        "centre_distance_m": float(np.linalg.norm(points[index] - target)),
        "ego_tangent_heading_deg": float(ego_heading_deg),
        "actor_heading_deg": float(actor_heading_deg),
        "absolute_heading_difference_deg": float(abs(signed_delta)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--ground-param", type=Path, required=True)
    parser.add_argument("--calibration-reference-run", type=Path, required=True)
    parser.add_argument("--actor-checkpoint", type=Path, required=True)
    parser.add_argument("--actor-dimensions", type=Path, required=True)
    parser.add_argument("--actor-id", default="audit_actor_placement")
    parser.add_argument("--actor-height-offset-m", type=float, default=-0.3)
    parser.add_argument("--frame-index", type=int, action="append", required=True)
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        metavar="LABEL=WORLD_X,WORLD_Z,HEADING_DEG",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata_path = args.metadata.expanduser().resolve()
    ground_path = args.ground_param.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    actor_checkpoint = args.actor_checkpoint.expanduser().resolve()
    actor_dimensions = args.actor_dimensions.expanduser().resolve()
    output = args.output.expanduser().resolve()
    frame_indices = [int(value) for value in args.frame_index]
    candidates = parse_candidate_specs(args.candidate)

    for path in (
        metadata_path,
        ground_path,
        calibration_run / "infos.pkl",
        actor_checkpoint,
        actor_dimensions,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    if frame_indices != sorted(set(frame_indices)):
        raise ValueError("frame indices must be unique and increasing")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.actor_id):
        raise ValueError("actor id must be alphanumeric with '_' or '-'")
    if not math.isfinite(args.actor_height_offset_m):
        raise ValueError("actor height offset must be finite")

    metadata: dict[str, Any] = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )
    with (calibration_run / "infos.pkl").open("rb") as stream:
        calibration_infos = pickle.load(stream)
    front_l2c = np.asarray(
        calibration_infos[0]["cam_params"]["CAM_FRONT"]["l2c"],
        dtype=np.float64,
    )
    if front_l2c.shape != (4, 4) or not np.isfinite(front_l2c).all():
        raise ValueError("calibration reference has invalid CAM_FRONT l2c")
    source_model_path = reference_model_path(metadata, front_l2c)
    frame_timestamps = {}
    for frame_index in frame_indices:
        records = select_camera_records(metadata, frame_index)
        frame_timestamps[str(frame_index)] = float(
            next(iter(records.values()))["timestamp"]
        )
    with ground_path.open("rb") as stream:
        camera_poses, camera_height, _ = pickle.load(stream)
    camera_poses = np.asarray(camera_poses, dtype=np.float64)
    dimensions = json.loads(actor_dimensions.read_text(encoding="utf-8"))

    output.mkdir(parents=True)
    reports = {}
    for label, (world_x, world_z, heading_deg) in candidates.items():
        transform = candidate_transform(
            world_x,
            world_z,
            heading_deg,
            camera_poses,
            float(camera_height),
            float(args.actor_height_offset_m),
        )
        transforms = {frame_index: transform for frame_index in frame_indices}
        modified = add_actor(
            metadata,
            frame_indices,
            args.actor_id,
            transforms,
        )
        metadata_output = output / f"metadata_{label}.json"
        metadata_output.write_text(
            json.dumps(modified, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        reports[label] = {
            "world_x_m": world_x,
            "world_z_m": world_z,
            "heading_deg_from_world_positive_z": heading_deg,
            "actor_world_transform": transform.astype(float).tolist(),
            "nearest_reference_path_relation": nearest_path_relation(
                source_model_path,
                world_x,
                world_z,
                heading_deg,
            ),
            "metadata": str(metadata_output),
            "metadata_sha256": sha256_file(metadata_output),
        }

    manifest = {
        "audit_id": "hugsim_actor_placement_setup_001",
        "date": date.today().isoformat(),
        "formal_evidence_eligible": False,
        "purpose": (
            "Choose a visible, ground-supported actor path before a separate "
            "prospective experiment is preregistered. SparseDrive outputs must "
            "not be inspected during this setup."
        ),
        "source_metadata": str(metadata_path),
        "source_metadata_sha256": sha256_file(metadata_path),
        "algorithm": {
            "name": "static exact-pose actor placement",
            "version": "0.2",
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "model_pose_rule": "CAM_FRONT.camtoworld @ CAM_FRONT.l2c",
            "heading_rule": "zero degrees is world +z; positive 90 degrees is world +x",
        },
        "ground_reference": {
            "path": str(ground_path),
            "sha256": sha256_file(ground_path),
            "camera_pose_count": int(len(camera_poses)),
            "camera_height_m": float(camera_height),
        },
        "calibration_reference": {
            "run": str(calibration_run),
            "infos": str(calibration_run / "infos.pkl"),
            "infos_sha256": sha256_file(calibration_run / "infos.pkl"),
            "front_l2c": front_l2c.astype(float).tolist(),
        },
        "reference_model_path": {
            "pose_count": len(source_model_path),
            "first": source_model_path[0],
            "last": source_model_path[-1],
        },
        "frame_indices": frame_indices,
        "frame_timestamps_s": frame_timestamps,
        "actor": {
            "id": args.actor_id,
            "motion": "static placement candidate; not a traffic behavior",
            "checkpoint": str(actor_checkpoint),
            "checkpoint_sha256": sha256_file(actor_checkpoint),
            "dimensions_wlh_m": dimensions,
            "dimensions_path": str(actor_dimensions),
            "dimensions_sha256": sha256_file(actor_dimensions),
            "height_offset_m": float(args.actor_height_offset_m),
        },
        "candidates": reports,
        "held_fixed": [
            "released metadata camera timestamps, intrinsics and poses",
            "background scene checkpoint",
            "native metadata dynamics",
            "actor identity, dimensions and height offset",
        ],
        "changed": "static actor world position and declared heading only",
        "selection_rule": (
            "Use only ground support, six-camera RGB placement, box orientation, "
            "background penetration and usable time-window gates. Do not select "
            "a candidate from SparseDrive planning response."
        ),
        "claim_boundary": (
            "This setup is excluded from formal evidence. It cannot establish "
            "lane legality, traffic-rule correctness, source-RGB equivalence, "
            "actor behavior realism, AD response validity or safety."
        ),
    }
    manifest_path = output / "actor_placement_setup_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
