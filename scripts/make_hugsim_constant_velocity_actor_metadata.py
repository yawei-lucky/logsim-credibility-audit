#!/usr/bin/env python3
"""Generate timestamp-explicit constant-velocity HUGSIM actor metadata.

The actor follows one straight world-space corridor.  Conditions may change
only the timestamp at which its centre reaches the fixed conflict centre.
This utility writes metadata and a geometry-only contract audit; it does not
run an AD receiver or qualify traffic behaviour.
"""

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

from make_hugsim_actor_placement_metadata import (
    candidate_transform,
    heading_vector,
)
from make_hugsim_lead_counterfactual_metadata import add_actor
from render_hugsim_exact_source_pose import select_camera_records, sha256_file


def parse_condition_specs(specs: list[str]) -> dict[str, float]:
    """Parse ``LABEL=ARRIVAL_TIMESTAMP_SECONDS`` conditions."""

    parsed: dict[str, float] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError("--condition must use LABEL=ARRIVAL_TIMESTAMP_SECONDS")
        label, raw_timestamp = spec.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or label in parsed:
            raise ValueError(f"invalid or duplicate condition label: {label!r}")
        timestamp = float(raw_timestamp)
        if not math.isfinite(timestamp):
            raise ValueError("arrival timestamp must be finite")
        parsed[label] = timestamp
    if not parsed:
        raise ValueError("at least one --condition is required")
    return parsed


def selected_timestamps(
    metadata: dict[str, Any], frame_indices: list[int]
) -> dict[int, float]:
    timestamps: dict[int, float] = {}
    for frame_index in frame_indices:
        records = select_camera_records(metadata, frame_index)
        timestamps[frame_index] = float(next(iter(records.values()))["timestamp"])
    values = np.asarray(list(timestamps.values()), dtype=np.float64)
    if not np.isfinite(values).all() or np.any(np.diff(values) <= 0.0):
        raise ValueError("selected metadata timestamps must be finite and increasing")
    return timestamps


def constant_velocity_transforms(
    timestamps: dict[int, float],
    conflict_xz: np.ndarray,
    heading_deg: float,
    speed_mps: float,
    arrival_timestamp_s: float,
    camera_poses: np.ndarray,
    camera_height: float,
    actor_height_offset_m: float,
) -> dict[int, np.ndarray]:
    """Create one transform per released timestamp with no hidden reset step."""

    if not math.isfinite(speed_mps) or speed_mps <= 0.0:
        raise ValueError("speed must be finite and positive")
    if not math.isfinite(arrival_timestamp_s):
        raise ValueError("arrival timestamp must be finite")
    conflict_xz = np.asarray(conflict_xz, dtype=np.float64)
    if conflict_xz.shape != (2,) or not np.isfinite(conflict_xz).all():
        raise ValueError("conflict centre must be a finite x-z pair")
    forward = heading_vector(heading_deg)
    return {
        frame_index: candidate_transform(
            *(conflict_xz + speed_mps * (timestamp - arrival_timestamp_s) * forward),
            heading_deg,
            camera_poses,
            camera_height,
            actor_height_offset_m,
        )
        for frame_index, timestamp in timestamps.items()
    }


def audit_constant_velocity(
    timestamps: dict[int, float],
    transforms: dict[int, np.ndarray],
    heading_deg: float,
    speed_mps: float,
    arrival_timestamp_s: float,
    conflict_xz: np.ndarray,
    tolerance_m: float = 1e-8,
) -> dict[str, Any]:
    frame_indices = list(timestamps)
    forward = heading_vector(heading_deg)
    rows = []
    maximum_step_residual = 0.0
    maximum_speed_error = 0.0
    maximum_lateral_residual = 0.0
    for position, frame_index in enumerate(frame_indices):
        transform = np.asarray(transforms[frame_index], dtype=np.float64)
        if transform.shape != (4, 4) or not np.isfinite(transform).all():
            raise ValueError(f"frame {frame_index}: invalid transform")
        world_xz = transform[[0, 2], 3]
        expected = np.asarray(conflict_xz, dtype=np.float64) + speed_mps * (
            timestamps[frame_index] - arrival_timestamp_s
        ) * forward
        position_residual = float(np.linalg.norm(world_xz - expected))
        maximum_lateral_residual = max(maximum_lateral_residual, position_residual)
        row: dict[str, Any] = {
            "frame_index": frame_index,
            "timestamp_s": timestamps[frame_index],
            "world_x_m": float(world_xz[0]),
            "world_y_m": float(transform[1, 3]),
            "world_z_m": float(world_xz[1]),
            "declared_position_residual_m": position_residual,
        }
        if position:
            previous_index = frame_indices[position - 1]
            dt = timestamps[frame_index] - timestamps[previous_index]
            displacement = world_xz - transforms[previous_index][[0, 2], 3]
            expected_displacement = speed_mps * dt * forward
            step_residual = float(np.linalg.norm(displacement - expected_displacement))
            measured_speed = float(np.linalg.norm(displacement) / dt)
            maximum_step_residual = max(maximum_step_residual, step_residual)
            maximum_speed_error = max(
                maximum_speed_error, abs(measured_speed - speed_mps)
            )
            row.update(
                {
                    "delta_t_s": dt,
                    "horizontal_displacement_m": float(np.linalg.norm(displacement)),
                    "measured_horizontal_speed_mps": measured_speed,
                    "step_residual_m": step_residual,
                }
            )
        rows.append(row)
    maximum_dt = float(
        np.max(np.diff(np.asarray(list(timestamps.values()), dtype=np.float64)))
    )
    passed = (
        maximum_step_residual <= tolerance_m
        and maximum_lateral_residual <= tolerance_m
        and maximum_speed_error <= tolerance_m
    )
    return {
        "passed": passed,
        "frame_count": len(frame_indices),
        "first_frame_index": frame_indices[0],
        "last_frame_index": frame_indices[-1],
        "duration_s": timestamps[frame_indices[-1]] - timestamps[frame_indices[0]],
        "maximum_timestamp_step_s": maximum_dt,
        "maximum_step_residual_m": maximum_step_residual,
        "maximum_declared_position_residual_m": maximum_lateral_residual,
        "maximum_horizontal_speed_error_mps": maximum_speed_error,
        "tolerance_m_or_mps": tolerance_m,
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--ground-param", type=Path, required=True)
    parser.add_argument("--actor-checkpoint", type=Path, required=True)
    parser.add_argument("--actor-dimensions", type=Path, required=True)
    parser.add_argument("--actor-id", default="audit_opposing_actor")
    parser.add_argument("--actor-height-offset-m", type=float, default=-0.3)
    parser.add_argument("--start-frame", type=int, required=True)
    parser.add_argument("--end-frame", type=int, required=True)
    parser.add_argument("--conflict-x", type=float, required=True)
    parser.add_argument("--conflict-z", type=float, required=True)
    parser.add_argument("--heading-deg", type=float, required=True)
    parser.add_argument("--speed-mps", type=float, required=True)
    parser.add_argument("--condition", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata_path = args.metadata.expanduser().resolve()
    ground_path = args.ground_param.expanduser().resolve()
    actor_checkpoint = args.actor_checkpoint.expanduser().resolve()
    actor_dimensions = args.actor_dimensions.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (metadata_path, ground_path, actor_checkpoint, actor_dimensions):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    if args.start_frame >= args.end_frame:
        raise ValueError("start frame must precede end frame")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.actor_id):
        raise ValueError("actor id must be alphanumeric with '_' or '-'")

    conditions = parse_condition_specs(args.condition)
    metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
    frame_indices = list(range(args.start_frame, args.end_frame + 1))
    timestamps = selected_timestamps(metadata, frame_indices)
    with ground_path.open("rb") as stream:
        camera_poses, camera_height, _ = pickle.load(stream)
    camera_poses = np.asarray(camera_poses, dtype=np.float64)
    dimensions = json.loads(actor_dimensions.read_text(encoding="utf-8"))
    conflict_xz = np.asarray([args.conflict_x, args.conflict_z], dtype=np.float64)

    output.mkdir(parents=True)
    condition_reports = {}
    for label, arrival_timestamp_s in conditions.items():
        transforms = constant_velocity_transforms(
            timestamps,
            conflict_xz,
            args.heading_deg,
            args.speed_mps,
            arrival_timestamp_s,
            camera_poses,
            float(camera_height),
            args.actor_height_offset_m,
        )
        audit = audit_constant_velocity(
            timestamps,
            transforms,
            args.heading_deg,
            args.speed_mps,
            arrival_timestamp_s,
            conflict_xz,
        )
        if not audit["passed"]:
            raise ValueError(f"{label}: generated trajectory failed its contract")
        modified = add_actor(metadata, frame_indices, args.actor_id, transforms)
        metadata_output = output / f"metadata_{label}.json"
        metadata_output.write_text(
            json.dumps(modified, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        condition_reports[label] = {
            "arrival_timestamp_s": arrival_timestamp_s,
            "metadata": str(metadata_output),
            "metadata_sha256": sha256_file(metadata_output),
            "actor_world_transform_by_frame": {
                str(frame_index): transforms[frame_index].astype(float).tolist()
                for frame_index in frame_indices
            },
            "motion_contract_audit": audit,
        }

    manifest = {
        "audit_id": "hugsim_opposing_path_dynamic_contract_001",
        "date": date.today().isoformat(),
        "formal_evidence_eligible": False,
        "source_metadata": str(metadata_path),
        "source_metadata_sha256": sha256_file(metadata_path),
        "frame_indices": frame_indices,
        "timestamps_s": {str(key): value for key, value in timestamps.items()},
        "timestamp_contract": "released metadata timestamps; no reset or hidden pre-step",
        "actor": {
            "id": args.actor_id,
            "checkpoint": str(actor_checkpoint),
            "checkpoint_sha256": sha256_file(actor_checkpoint),
            "dimensions_wlh_m": dimensions,
            "dimensions_path": str(actor_dimensions),
            "dimensions_sha256": sha256_file(actor_dimensions),
            "height_offset_m": args.actor_height_offset_m,
            "corridor": {
                "conflict_centre_world_xz_m": conflict_xz.tolist(),
                "heading_deg_from_world_positive_z": args.heading_deg,
                "speed_mps": args.speed_mps,
            },
        },
        "conditions": condition_reports,
        "held_fixed": [
            "released timestamps, six-camera intrinsics and poses",
            "background scene and native dynamics",
            "actor identity, dimensions, speed, heading and corridor",
        ],
        "changed": "actor conflict-centre arrival timestamp only",
        "claim_boundary": (
            "This dry run qualifies explicit transform timing and continuity only. "
            "It does not qualify lane legality, traffic behaviour, RGB projection, "
            "real-sensor equivalence, AD response or safety."
        ),
    }
    manifest_path = output / "dynamic_contract_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
