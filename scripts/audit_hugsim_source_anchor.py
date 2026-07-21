#!/usr/bin/env python3
"""Audit whether a released HUGSIM scene can support a real-sim anchor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import yaml
from PIL import Image, UnidentifiedImageError
from scipy.spatial.transform import Rotation


NUSCENES_CAMERAS = (
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_matrix(value: Any, shape: tuple[int, int], field: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != shape or not np.isfinite(matrix).all():
        raise ValueError(f"{field} must be a finite {shape[0]}x{shape[1]} matrix")
    return matrix


def require_intrinsics(value: Any, field: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.shape not in {(3, 3), (4, 4)} or not np.isfinite(matrix).all():
        raise ValueError(f"{field} must be a finite 3x3 or 4x4 matrix")
    return matrix[:3, :3]


def valid_camera_geometry(frame: dict[str, Any]) -> bool:
    try:
        pose = require_matrix(frame["camtoworld"], (4, 4), "frame.camtoworld")
        intrinsics = require_intrinsics(frame["intrinsics"], "frame.intrinsics")
        width = int(frame["width"])
        height = int(frame["height"])
    except (KeyError, TypeError, ValueError):
        return False
    rotation = pose[:3, :3]
    return bool(
        width > 0
        and height > 0
        and intrinsics[0, 0] > 0
        and intrinsics[1, 1] > 0
        and 0 <= intrinsics[0, 2] <= width
        and 0 <= intrinsics[1, 2] <= height
        and np.allclose(pose[3], [0, 0, 0, 1], atol=1e-6)
        and np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5)
        and math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-5)
    )


def valid_dynamic_poses(frame: dict[str, Any]) -> bool:
    dynamics = frame.get("dynamics", {})
    if not isinstance(dynamics, dict):
        return False
    for pose_value in dynamics.values():
        try:
            pose = require_matrix(pose_value, (4, 4), "frame.dynamics pose")
        except ValueError:
            return False
        rotation = pose[:3, :3]
        if not (
            np.allclose(pose[3], [0, 0, 0, 1], atol=1e-6)
            and np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5)
            and math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-5)
        ):
            return False
    return True


def inspect_rgb(path: Path, expected_size: tuple[int, int]) -> tuple[bool, str | None]:
    try:
        with Image.open(path) as image:
            size = image.size
            band_count = len(image.getbands())
            image.verify()
        if size != expected_size:
            return False, f"size {size} != metadata {expected_size}"
        if band_count < 3:
            return False, f"only {band_count} image channel(s)"
    except (OSError, UnidentifiedImageError, ValueError) as error:
        return False, f"decode failed: {error}"
    return True, None


def git_commit(repo: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def frame_camera(frame: dict[str, Any]) -> str:
    rgb_path = frame.get("rgb_path")
    if not isinstance(rgb_path, str):
        raise ValueError("frame.rgb_path must be a string")
    path = PurePosixPath(rgb_path)
    if len(path.parts) < 2:
        raise ValueError(f"cannot infer camera from {rgb_path!r}")
    return path.parent.name


def resolve_frame_path(source_root: Path, rgb_path: str) -> Path:
    relative = PurePosixPath(rgb_path.removeprefix("./"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe frame path {rgb_path!r}")
    return source_root.joinpath(*relative.parts)


def auxiliary_paths(rgb_path: Path) -> dict[str, Path]:
    parts = list(rgb_path.parts)
    try:
        image_index = parts.index("images")
    except ValueError:
        return {}
    paths = {}
    for modality, suffix in (
        ("semantic", ".npy"),
        ("depth", ".pt"),
        ("mask", ".npy"),
    ):
        derived = parts.copy()
        derived[image_index] = {
            "semantic": "semantics",
            "depth": "depth",
            "mask": "masks",
        }[modality]
        paths[modality] = Path(*derived).with_suffix(suffix)
    flow = parts.copy()
    flow[image_index] = "flow"
    paths["flow"] = Path(*flow).with_name(
        f"{Path(flow[-1]).stem}_flow.npy"
    )
    return paths


def rt_matrix(euler_deg: Any, translation: Any) -> np.ndarray:
    pose = np.eye(4)
    pose[:3, :3] = Rotation.from_euler(
        "XYZ", np.asarray(euler_deg, dtype=float), degrees=True
    ).as_matrix()
    pose[:3, 3] = np.asarray(translation, dtype=float)
    return pose


def compare_sim_camera_template(
    frames: list[dict[str, Any]], camera_yaml: Path
) -> dict[str, Any]:
    with camera_yaml.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    cameras = config["cams"]
    first_timestamp = min(float(frame["timestamp"]) for frame in frames)
    first_frames = {
        frame_camera(frame): frame
        for frame in frames
        if float(frame["timestamp"]) == first_timestamp
    }
    front_meta = require_matrix(
        first_frames["CAM_FRONT"]["camtoworld"],
        (4, 4),
        "CAM_FRONT.camtoworld",
    )
    front_cfg = cameras["CAM_FRONT"]["extrinsics"]
    vehicle_to_front = rt_matrix(
        front_cfg["v2c_rot"], front_cfg["v2c_trans"]
    )
    rect_cfg = config.get(
        "cam_rect", {"rot": [0, 0, 0], "trans": [0, 0, 0]}
    )
    rect = rt_matrix(rect_cfg["rot"], rect_cfg["trans"])

    comparisons = {}
    for camera in NUSCENES_CAMERAS:
        frame = first_frames[camera]
        meta_pose = require_matrix(
            frame["camtoworld"], (4, 4), f"{camera}.camtoworld"
        )
        meta_relative = np.linalg.inv(front_meta) @ meta_pose
        camera_cfg = cameras[camera]
        extrinsics = camera_cfg["extrinsics"]
        vehicle_to_camera = rt_matrix(
            extrinsics["v2c_rot"], extrinsics["v2c_trans"]
        )
        sim_relative = vehicle_to_front @ np.linalg.inv(vehicle_to_camera) @ rect
        delta = np.linalg.inv(meta_relative) @ sim_relative

        intrinsics = camera_cfg["intrinsics"]
        width = int(intrinsics["W"])
        height = int(intrinsics["H"])
        sim_fx = width / (
            2 * math.tan(math.radians(float(intrinsics["fovx"])) / 2)
        )
        sim_fy = height / (
            2 * math.tan(math.radians(float(intrinsics["fovy"])) / 2)
        )
        meta_k = require_intrinsics(frame["intrinsics"], f"{camera}.K")
        comparisons[camera] = {
            "translation_difference_m": float(np.linalg.norm(delta[:3, 3])),
            "rotation_difference_deg": float(
                math.degrees(Rotation.from_matrix(delta[:3, :3]).magnitude())
            ),
            "maximum_focal_difference_px": float(
                max(abs(sim_fx - meta_k[0, 0]), abs(sim_fy - meta_k[1, 1]))
            ),
            "maximum_principal_point_difference_px": float(
                max(
                    abs(float(intrinsics["cx"]) - meta_k[0, 2]),
                    abs(float(intrinsics["cy"]) - meta_k[1, 2]),
                )
            ),
            "simulation_resolution": [width, height],
            "metadata_resolution": [int(frame["width"]), int(frame["height"])],
        }

    maximum_translation = max(
        item["translation_difference_m"] for item in comparisons.values()
    )
    maximum_rotation = max(
        item["rotation_difference_deg"] for item in comparisons.values()
    )
    maximum_focal = max(
        item["maximum_focal_difference_px"] for item in comparisons.values()
    )
    maximum_principal = max(
        item["maximum_principal_point_difference_px"]
        for item in comparisons.values()
    )
    resolutions_match = all(
        item["simulation_resolution"] == item["metadata_resolution"]
        for item in comparisons.values()
    )
    exact_within_tolerance = bool(
        resolutions_match
        and maximum_translation <= 1e-6
        and maximum_rotation <= 1e-6
        and maximum_focal <= 1e-6
        and maximum_principal <= 1e-6
    )

    return {
        "camera_yaml": str(camera_yaml.resolve()),
        "camera_yaml_sha256": sha256_file(camera_yaml),
        "comparison_timestamp_s": first_timestamp,
        "cam_rect_translation": list(rect_cfg["trans"]),
        "maximum_translation_difference_m": maximum_translation,
        "maximum_rotation_difference_deg": maximum_rotation,
        "maximum_focal_difference_px": maximum_focal,
        "maximum_principal_point_difference_px": maximum_principal,
        "all_resolutions_match": resolutions_match,
        "per_camera": comparisons,
        "matched_pose_decision": (
            "exact_within_1e-6" if exact_within_tolerance else "not_exact"
        ),
    }


def audit_scene_anchor(
    scene_dir: Path,
    source_root: Path | None = None,
    camera_yaml: Path | None = None,
    sim_run: Path | None = None,
    dataset_reader: Path | None = None,
    hugsim_repo: Path | None = None,
) -> dict[str, Any]:
    scene_dir = scene_dir.resolve()
    source_root = (source_root or scene_dir).resolve()
    metadata_path = scene_dir / "meta_data.json"
    with metadata_path.open("r", encoding="utf-8") as stream:
        metadata = json.load(stream)
    frames = metadata.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("meta_data.frames must be a non-empty list")

    camera_counts: Counter[str] = Counter()
    timestamps: defaultdict[float, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    rgb_existing = 0
    rgb_valid = 0
    rgb_manifest = hashlib.sha256()
    invalid_rgb_examples = []
    modality_existing: Counter[str] = Counter()
    all_camera_geometry_valid = True
    all_dynamic_poses_valid = True
    provenance_fields = set()
    rgb_paths = []
    frame_timestamp_sequence = []
    sample_data_tokens = []
    sample_tokens = []
    missing_source_identity_count = 0
    for index, frame in enumerate(frames):
        camera = frame_camera(frame)
        camera_counts[camera] += 1
        timestamp = float(frame["timestamp"])
        if not math.isfinite(timestamp):
            raise ValueError("frame.timestamp must be finite")
        frame_timestamp_sequence.append(timestamp)
        timestamps[timestamp].append((index, frame))
        rgb_path = resolve_frame_path(source_root, frame["rgb_path"])
        rgb_paths.append(frame["rgb_path"])
        if rgb_path.is_file():
            rgb_existing += 1
            valid_rgb, error = inspect_rgb(
                rgb_path, (int(frame["width"]), int(frame["height"]))
            )
            if valid_rgb:
                rgb_valid += 1
                rgb_manifest.update(frame["rgb_path"].encode("utf-8"))
                rgb_manifest.update(sha256_file(rgb_path).encode("ascii"))
            elif len(invalid_rgb_examples) < 10:
                invalid_rgb_examples.append(
                    {"rgb_path": frame["rgb_path"], "reason": error}
                )
        for modality, path in auxiliary_paths(rgb_path).items():
            modality_existing[modality] += int(path.is_file())
        all_camera_geometry_valid &= valid_camera_geometry(frame)
        all_dynamic_poses_valid &= valid_dynamic_poses(frame)
        sample_data_token = frame.get("sample_data_token")
        sample_token = frame.get("sample_token")
        if sample_data_token not in (None, ""):
            provenance_fields.add("sample_data_token")
            sample_data_tokens.append(str(sample_data_token))
        if sample_token not in (None, ""):
            provenance_fields.add("sample_token")
            sample_tokens.append(str(sample_token))
        if sample_data_token in (None, "") and sample_token in (None, ""):
            missing_source_identity_count += 1

    sorted_timestamps = sorted(timestamps)
    time_deltas = np.diff(sorted_timestamps)
    timestamp_groups_complete = True
    group_frame_indices = []
    group_sample_tokens = []
    reader_test_candidates = []
    for timestamp in sorted_timestamps:
        group = timestamps[timestamp]
        group_cameras = [frame_camera(item[1]) for item in group]
        group_frame_index_values = {
            PurePosixPath(item[1]["rgb_path"]).stem for item in group
        }
        if not (
            len(group) == len(NUSCENES_CAMERAS)
            and set(group_cameras) == set(NUSCENES_CAMERAS)
            and len(group_frame_index_values) == 1
        ):
            timestamp_groups_complete = False
        if len(group_frame_index_values) == 1:
            try:
                group_frame_indices.append(int(next(iter(group_frame_index_values))))
            except ValueError:
                timestamp_groups_complete = False
        tokens_in_group = {
            str(item[1]["sample_token"])
            for item in group
            if item[1].get("sample_token") not in (None, "")
        }
        if tokens_in_group:
            if len(tokens_in_group) != 1 or len(group) != len(NUSCENES_CAMERAS):
                timestamp_groups_complete = False
            else:
                group_sample_tokens.append(next(iter(tokens_in_group)))
        if group and all(index % 30 >= 24 for index, _ in group):
            reader_test_candidates.append(
                {
                    "timestamp_s": timestamp,
                    "frame_index": int(
                        PurePosixPath(group[0][1]["rgb_path"]).stem
                    ),
                    "camera_count": len(group),
                    "rgb_paths": [item[1]["rgb_path"] for item in group],
                    "all_real_rgb_present": all(
                        resolve_frame_path(source_root, item[1]["rgb_path"]).is_file()
                        for item in group
                    ),
                }
            )

    cfg_path = scene_dir / "cfg.yaml"
    cfg = {}
    if cfg_path.is_file():
        with cfg_path.open("r", encoding="utf-8") as stream:
            cfg = yaml.safe_load(stream) or {}

    dynamic_files = sorted(scene_dir.glob("dynamic_*.pth"))
    native_dynamic_ids = sorted(metadata.get("verts", {}))
    dynamic_model_ids = {
        path.stem.removeprefix("dynamic_") for path in dynamic_files
    }
    frame_dynamic_ids = {
        dynamic_id
        for frame in frames
        for dynamic_id in frame.get("dynamics", {})
    }
    dynamics_complete = bool(
        all_dynamic_poses_valid
        and frame_dynamic_ids.issubset(set(native_dynamic_ids))
        and set(native_dynamic_ids).issubset(dynamic_model_ids)
    )
    sample_data_identity_complete = bool(
        len(sample_data_tokens) == len(frames)
        and len(set(sample_data_tokens)) == len(frames)
    )
    sample_identity_complete = bool(
        len(sample_tokens) == len(frames)
        and len(group_sample_tokens) == len(sorted_timestamps)
        and len(set(group_sample_tokens)) == len(sorted_timestamps)
    )
    source_identity_complete = bool(
        missing_source_identity_count == 0
        and (sample_data_identity_complete or sample_identity_complete)
    )
    rgb_paths_unique = len(set(rgb_paths)) == len(frames)
    frame_indices_strictly_increasing = bool(
        len(group_frame_indices) == len(sorted_timestamps)
        and (
            len(group_frame_indices) <= 1
            or np.all(np.diff(group_frame_indices) > 0)
        )
    )
    frame_records_time_ordered = bool(
        len(frame_timestamp_sequence) <= 1
        or np.all(np.diff(frame_timestamp_sequence) >= 0)
    )
    metadata_complete = (
        set(camera_counts) == set(NUSCENES_CAMERAS)
        and len(set(camera_counts.values())) == 1
        and all_camera_geometry_valid
        and timestamp_groups_complete
        and rgb_paths_unique
        and frame_indices_strictly_increasing
        and frame_records_time_ordered
        and bool(len(sorted_timestamps))
        and bool(np.all(time_deltas > 0))
        and dynamics_complete
    )
    gate_reasons = []
    if rgb_existing != len(frames):
        gate_reasons.append("referenced real RGB files are incomplete")
    elif rgb_valid != len(frames):
        gate_reasons.append("real RGB files fail decode, size, or channel validation")
    if not source_identity_complete:
        gate_reasons.append("per-frame source sample/sample_data identity is incomplete or non-unique")
    if not metadata_complete:
        gate_reasons.append("camera groups, geometry, timing, or native dynamics are incomplete")

    result: dict[str, Any] = {
        "audit_id": "hugsim_source_anchor_gate",
        "audit_environment": {
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "hugsim_repo": str(hugsim_repo.resolve()) if hugsim_repo else None,
            "hugsim_commit": git_commit(hugsim_repo.resolve())
            if hugsim_repo
            else None,
            "dataset_reader_path": str(dataset_reader.resolve())
            if dataset_reader
            else None,
            "dataset_reader_sha256": sha256_file(dataset_reader.resolve())
            if dataset_reader
            else None,
        },
        "scene_dir": str(scene_dir),
        "source_root": str(source_root),
        "metadata": {
            "path": str(metadata_path),
            "sha256": sha256_file(metadata_path),
            "frame_record_count": len(frames),
            "timestamp_count": len(sorted_timestamps),
            "timestamp_range_s": [sorted_timestamps[0], sorted_timestamps[-1]],
            "median_timestep_s": float(np.median(time_deltas))
            if len(time_deltas)
            else None,
            "camera_counts": dict(sorted(camera_counts.items())),
            "all_camera_geometry_valid": all_camera_geometry_valid,
            "timestamp_groups_complete": timestamp_groups_complete,
            "rgb_paths_unique": rgb_paths_unique,
            "frame_indices_strictly_increasing": frame_indices_strictly_increasing,
            "frame_records_time_ordered": frame_records_time_ordered,
            "native_dynamic_ids": native_dynamic_ids,
            "native_dynamic_files": [str(path) for path in dynamic_files],
            "native_dynamics_complete": dynamics_complete,
            "reader_split_rule": "current dataset_readers.py: idx % 30 >= 24",
            "reader_test_candidate_timestamp_count": len(reader_test_candidates),
            "first_reader_test_candidates": reader_test_candidates[:5],
            "checkpoint_training_exclusion_confirmed": False,
        },
        "source_observations": {
            "expected_real_rgb_count": len(frames),
            "existing_real_rgb_count": rgb_existing,
            "valid_real_rgb_count": rgb_valid,
            "invalid_real_rgb_examples": invalid_rgb_examples,
            "real_rgb_manifest_sha256": (
                rgb_manifest.hexdigest() if rgb_valid else None
            ),
            "existing_semantic_count": modality_existing["semantic"],
            "existing_depth_count": modality_existing["depth"],
            "existing_mask_count": modality_existing["mask"],
            "existing_flow_count": modality_existing["flow"],
            "provenance_fields": sorted(provenance_fields),
            "missing_source_identity_count": missing_source_identity_count,
            "unique_sample_data_token_count": len(set(sample_data_tokens)),
            "unique_sample_token_count": len(set(sample_tokens)),
            "sample_data_identity_complete": sample_data_identity_complete,
            "sample_identity_complete": sample_identity_complete,
            "source_identity_complete": source_identity_complete,
            "configured_private_source_path": cfg.get("source_path"),
        },
        "gate": {
            "status": "ready" if not gate_reasons else "blocked",
            "reasons": gate_reasons,
            "permitted_claim": (
                "complete real-sim anchor candidate"
                if not gate_reasons
                else "metadata-only frame-index candidate"
            ),
        },
    }
    if camera_yaml is not None:
        result["standard_sim_camera_comparison"] = compare_sim_camera_template(
            frames, camera_yaml.resolve()
        )
    if sim_run is not None:
        sim_run = sim_run.resolve()
        summary_path = sim_run / "audit_summary.json"
        summary = {}
        if summary_path.is_file():
            with summary_path.open("r", encoding="utf-8") as stream:
                summary = json.load(stream)
        result["existing_simulation_output"] = {
            "run": str(sim_run),
            "audit_summary_exists": summary_path.is_file(),
            "observations_pickle_exists": (sim_run / "observations.pkl").is_file(),
            "run_status": summary.get("run_status"),
            "camera_names": summary.get("camera_names"),
            "observation_modalities": summary.get("observation_modalities"),
            "matched_real_sim_status": "not_paired",
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--camera-yaml", type=Path)
    parser.add_argument("--sim-run", type=Path)
    parser.add_argument("--dataset-reader", type=Path)
    parser.add_argument("--hugsim-repo", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit_scene_anchor(
        scene_dir=args.scene_dir,
        source_root=args.source_root,
        camera_yaml=args.camera_yaml,
        sim_run=args.sim_run,
        dataset_reader=args.dataset_reader,
        hugsim_repo=args.hugsim_repo,
    )
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=False)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["gate"]["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
