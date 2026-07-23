#!/usr/bin/env python3
"""Add one source-path-locked lead vehicle to an exact-source-pose window."""

from __future__ import annotations

import argparse
import copy
import json
import math
import pickle
import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from render_hugsim_exact_source_pose import (
    select_camera_records,
    sha256_file,
)


def parse_condition_specs(specs: list[str]) -> dict[str, float]:
    parsed = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError("--condition must use LABEL=FORWARD_PATH_GAP_METRES")
        label, raw_distance = spec.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or label in parsed:
            raise ValueError(f"invalid or duplicate condition label: {label!r}")
        distance = float(raw_distance)
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError("lead path gap must be finite and positive")
        parsed[label] = distance
    if not parsed:
        raise ValueError("at least one condition is required")
    return parsed


def model_to_world(
    metadata: dict[str, Any],
    frame_index: int,
    front_l2c: np.ndarray,
) -> np.ndarray:
    records = select_camera_records(metadata, frame_index)
    transform = (
        np.asarray(records["CAM_FRONT"]["camtoworld"], dtype=np.float64)
        @ front_l2c
    )
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise ValueError(f"invalid model pose at frame {frame_index}")
    return transform


def ground_height(
    camera_poses: np.ndarray,
    camera_height: float,
    world_x: float,
    world_z: float,
) -> float:
    distances = np.sqrt(
        (camera_poses[:, 0, 3] - world_x) ** 2
        + (camera_poses[:, 2, 3] - world_z) ** 2
    )
    nearest = camera_poses[int(np.argmin(distances))]
    world_to_camera = np.linalg.inv(nearest)
    local = (
        world_to_camera[:3, :3] @ np.asarray([world_x, 0.0, world_z])
        + world_to_camera[:3, 3]
    )
    local[1] = 0.0
    projected_world = nearest[:3, :3] @ local + nearest[:3, 3]
    return float(projected_world[1] + camera_height)


def rotation_y(angle: float) -> np.ndarray:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return np.asarray(
        [
            [cosine, 0.0, sine],
            [0.0, 1.0, 0.0],
            [-sine, 0.0, cosine],
        ],
        dtype=np.float64,
    )


def lead_transform(
    world_xz: np.ndarray,
    forward_xz: np.ndarray,
    camera_poses: np.ndarray,
    camera_height: float,
    actor_height_offset_m: float,
) -> np.ndarray:
    world_xz = np.asarray(world_xz, dtype=np.float64)
    forward_xz = np.asarray(forward_xz, dtype=np.float64)
    if world_xz.shape != (2,) or forward_xz.shape != (2,):
        raise ValueError("lead position and forward direction must be x-z pairs")
    norm = float(np.linalg.norm(forward_xz))
    if norm < 1e-6:
        raise ValueError("lead forward direction has no horizontal component")
    forward_xz /= norm
    heading = math.atan2(float(forward_xz[0]), float(forward_xz[1]))
    world_x, world_z = (float(value) for value in world_xz)
    transform = np.eye(4, dtype=np.float64)
    # HUGSIM RealCar local +x is its longitudinal axis. The released planner
    # maps yaw zero to world +z with R_y(-pi/2).
    transform[:3, :3] = rotation_y(heading - math.pi / 2.0)
    transform[:3, 3] = [
        world_x,
        ground_height(
            camera_poses,
            camera_height,
            world_x,
            world_z,
        )
        + actor_height_offset_m,
        world_z,
    ]
    return transform


def path_lead_anchor(
    metadata: dict[str, Any],
    anchor_frame_index: int,
    path_distance_m: float,
    front_l2c: np.ndarray,
) -> dict[str, Any]:
    available = sorted(
        {
            int(Path(frame["rgb_path"]).stem)
            for frame in metadata.get("frames", [])
            if Path(frame["rgb_path"]).parent.name == "CAM_FRONT"
            and int(Path(frame["rgb_path"]).stem) >= anchor_frame_index
        }
    )
    if not available or available[0] != anchor_frame_index:
        raise ValueError("anchor frame is absent from the source trajectory")
    poses = {
        index: model_to_world(metadata, index, front_l2c)
        for index in available
    }
    accumulated = 0.0
    previous_index = available[0]
    previous_xz = poses[previous_index][[0, 2], 3]
    for current_index in available[1:]:
        current_xz = poses[current_index][[0, 2], 3]
        segment = current_xz - previous_xz
        segment_length = float(np.linalg.norm(segment))
        if segment_length > 1e-9 and accumulated + segment_length >= path_distance_m:
            fraction = (path_distance_m - accumulated) / segment_length
            world_xz = previous_xz + fraction * segment
            return {
                "world_xz": world_xz,
                "forward_xz": segment / segment_length,
                "bracketing_frames": [previous_index, current_index],
                "interpolation_fraction": float(fraction),
                "path_distance_m": float(path_distance_m),
            }
        accumulated += segment_length
        previous_index = current_index
        previous_xz = current_xz
    raise ValueError(
        f"source trajectory has only {accumulated:.3f} m after frame "
        f"{anchor_frame_index}, less than requested {path_distance_m:.3f} m"
    )


def add_actor(
    metadata: dict[str, Any],
    frame_indices: list[int],
    actor_id: str,
    actor_transforms: dict[int, np.ndarray],
) -> dict[str, Any]:
    result = copy.deepcopy(metadata)
    expected = {
        (frame_index, camera)
        for frame_index in frame_indices
        for camera in select_camera_records(metadata, frame_index)
    }
    changed = set()
    for frame in result.get("frames", []):
        path = Path(frame["rgb_path"])
        frame_index = int(path.stem)
        camera = path.parent.name
        if (frame_index, camera) not in expected:
            continue
        dynamics = frame.setdefault("dynamics", {})
        if actor_id in dynamics:
            raise ValueError(f"actor id already exists in frame dynamics: {actor_id}")
        dynamics[actor_id] = actor_transforms[frame_index].astype(float).tolist()
        changed.add((frame_index, camera))
    if changed != expected:
        raise ValueError(f"failed to inject complete camera groups: {expected - changed}")
    return result


def relative_actor_geometry(
    metadata: dict[str, Any],
    frame_indices: list[int],
    front_l2c: np.ndarray,
    actor_transforms: dict[int, np.ndarray],
) -> list[dict[str, float]]:
    rows = []
    for frame_index in frame_indices:
        actor_world = actor_transforms[frame_index][:3, 3]
        pose = model_to_world(metadata, frame_index, front_l2c)
        relative = np.linalg.inv(pose) @ np.append(actor_world, 1.0)
        rows.append(
            {
                "source_frame_index": frame_index,
                "right_m": float(relative[0]),
                "forward_m": float(relative[1]),
                "up_m": float(relative[2]),
                "planar_distance_m": float(np.linalg.norm(relative[:2])),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--calibration-reference-run", type=Path, required=True)
    parser.add_argument("--ground-param", type=Path, required=True)
    parser.add_argument("--actor-checkpoint", type=Path, required=True)
    parser.add_argument("--actor-dimensions", type=Path, required=True)
    parser.add_argument("--actor-id", default="audit_stationary_lead")
    parser.add_argument("--actor-height-offset-m", type=float, default=-0.3)
    parser.add_argument("--frame-index", type=int, action="append", required=True)
    parser.add_argument("--condition", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata_path = args.metadata.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    ground_path = args.ground_param.expanduser().resolve()
    actor_checkpoint = args.actor_checkpoint.expanduser().resolve()
    actor_dimensions = args.actor_dimensions.expanduser().resolve()
    output = args.output.expanduser().resolve()
    frame_indices = [int(value) for value in args.frame_index]
    conditions = parse_condition_specs(args.condition)

    for path in (
        metadata_path,
        calibration_run / "infos.pkl",
        ground_path,
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

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with (calibration_run / "infos.pkl").open("rb") as stream:
        calibration_infos = pickle.load(stream)
    front_l2c = np.asarray(
        calibration_infos[0]["cam_params"]["CAM_FRONT"]["l2c"],
        dtype=np.float64,
    )
    with ground_path.open("rb") as stream:
        camera_poses, camera_height, _ = pickle.load(stream)
    camera_poses = np.asarray(camera_poses, dtype=np.float64)
    dimensions = json.loads(actor_dimensions.read_text(encoding="utf-8"))

    output.mkdir(parents=True)
    condition_reports = {}
    for label, distance in conditions.items():
        path_anchors = {}
        transforms = {}
        for frame_index in frame_indices:
            path_anchor = path_lead_anchor(
                metadata,
                frame_index,
                distance,
                front_l2c,
            )
            path_anchors[frame_index] = path_anchor
            transforms[frame_index] = lead_transform(
                path_anchor["world_xz"],
                path_anchor["forward_xz"],
                camera_poses,
                float(camera_height),
                float(args.actor_height_offset_m),
            )
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
        condition_reports[label] = {
            "declared_forward_path_gap_m": distance,
            "source_path_anchor_by_frame": {
                str(frame_index): {
                    key: (
                        value.astype(float).tolist()
                        if isinstance(value, np.ndarray)
                        else value
                    )
                    for key, value in path_anchors[frame_index].items()
                }
                for frame_index in frame_indices
            },
            "actor_world_transform_by_frame": {
                str(frame_index): transforms[frame_index].astype(float).tolist()
                for frame_index in frame_indices
            },
            "actor_relative_geometry": relative_actor_geometry(
                metadata,
                frame_indices,
                front_l2c,
                transforms,
            ),
            "metadata": str(metadata_output),
            "metadata_sha256": sha256_file(metadata_output),
        }

    manifest = {
        "audit_id": "hugsim_same_window_lead_counterfactual_metadata_001",
        "date": date.today().isoformat(),
        "source_metadata": str(metadata_path),
        "source_metadata_sha256": sha256_file(metadata_path),
        "frame_indices": frame_indices,
        "anchor_frame_index": frame_indices[0],
        "actor": {
            "id": args.actor_id,
            "motion": (
                "scripted along the recorded source camera-rig path at a "
                "constant forward arc-length gap"
            ),
            "checkpoint": str(actor_checkpoint),
            "checkpoint_sha256": sha256_file(actor_checkpoint),
            "dimensions_wlh_m": dimensions,
            "dimensions_path": str(actor_dimensions),
            "dimensions_sha256": sha256_file(actor_dimensions),
            "height_offset_m": float(args.actor_height_offset_m),
        },
        "conditions": condition_reports,
        "held_fixed": [
            "source camera timestamps",
            "six camera intrinsics and poses",
            "background scene checkpoint",
            "native reconstructed dynamics",
            "lead vehicle asset and source-path centreline",
        ],
        "changed": "lead vehicle forward path gap only",
        "claim_boundary": (
            "These are designed counterfactual stimuli with no matched real "
            "counterpart. The transform uses source camera-rig geometry and "
            "HUGSIM's ground model. The scripted actor does not respond to "
            "ego or traffic, so this does not establish realistic traffic "
            "behavior, physical truth or safety."
        ),
    }
    manifest_path = output / "counterfactual_metadata_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
