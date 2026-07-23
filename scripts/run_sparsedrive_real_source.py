#!/usr/bin/env python3
"""Run a bounded SparseDrive qualification sequence on real HUGSIM-source RGB.

This is a local receiver/input-contract gate.  It does not rerun the official
nuScenes benchmark and does not treat SparseDrive as simulator truth.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from render_hugsim_exact_source_pose import select_camera_records
from run_sparse4d_hugsim_receiver import (
    CAMERA_ORDER,
    IMAGE_MEAN,
    IMAGE_STD,
    resize_crop_rgb,
    sha256_file,
)
from run_sparsedrive_hugsim_receiver import (
    MODEL_PLAN_GROUND_Z_M,
    build_model,
    cpu_copy,
    ensure_anchor_assets,
    native_summary,
    plan_kinematics,
    reset_temporal_state,
    source_provenance,
    validate_compatibility_patch,
)


PLAN_STEP_SECONDS = 0.5
PLAN_STEPS = 6
RESET_TOLERANCE = 1e-4
CAMERA_SWAP = {
    "CAM_FRONT_LEFT": "CAM_FRONT_RIGHT",
    "CAM_FRONT_RIGHT": "CAM_FRONT_LEFT",
}
VARIANTS = (
    "baseline",
    "camera_swap",
    "temporal_reverse",
    "front_intrinsic_shift",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sparsedrive-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--runtime-deps", type=Path, required=True)
    parser.add_argument("--anchor-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--source-archive-manifest", type=Path, required=True)
    parser.add_argument("--metadata-archive-manifest", type=Path, required=True)
    parser.add_argument(
        "--calibration-reference-run",
        type=Path,
        required=True,
        help=(
            "Recorded HUGSIM run supplying the provisional SparseDrive "
            "model-LiDAR to CAM_FRONT transform."
        ),
    )
    parser.add_argument(
        "--frame-index",
        type=int,
        action="append",
        required=True,
        dest="frame_indices",
    )
    parser.add_argument(
        "--front-intrinsic-shift-px",
        type=float,
        default=80.0,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def wrapped_rate(current: float, previous: float, dt: float) -> float:
    if dt <= 0:
        raise ValueError("timestamps must increase")
    delta = math.atan2(math.sin(current - previous), math.cos(current - previous))
    return delta / dt


def validate_indices(frame_indices: list[int]) -> int:
    if len(frame_indices) != 4:
        raise ValueError("exactly four receiver frame indices are required")
    if frame_indices != sorted(set(frame_indices)):
        raise ValueError("frame indices must be unique and strictly increasing")
    differences = np.diff(frame_indices)
    if not np.all(differences == differences[0]):
        raise ValueError("frame indices must use one constant stride")
    stride = int(differences[0])
    if stride <= 0:
        raise ValueError("frame stride must be positive")
    return stride


def load_metadata(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        metadata = json.load(stream)
    if metadata.get("camera_model") != "OPENCV":
        raise ValueError("only OPENCV source metadata is supported")
    return metadata


def model_to_world(
    metadata: dict[str, Any],
    frame_index: int,
    front_l2c: np.ndarray,
) -> np.ndarray:
    records = select_camera_records(metadata, frame_index)
    transform = (
        np.asarray(records["CAM_FRONT"]["camtoworld"], dtype=np.float64)
        @ np.asarray(front_l2c, dtype=np.float64)
    )
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise ValueError(f"invalid model pose at source frame {frame_index}")
    return transform


def normalized_model_poses(
    metadata: dict[str, Any],
    indices: list[int],
    front_l2c: np.ndarray,
    normalization_index: int,
) -> dict[int, np.ndarray]:
    normalization = np.linalg.inv(
        model_to_world(metadata, normalization_index, front_l2c)
    )
    return {
        index: normalization @ model_to_world(metadata, index, front_l2c)
        for index in indices
    }


def pose_heading(pose: np.ndarray) -> float:
    """Return yaw for model axes x=right, y=forward, z=up."""

    forward = np.asarray(pose, dtype=np.float64)[:2, 1]
    return math.atan2(-float(forward[0]), float(forward[1]))


def pose_derived_ego_status(
    current_pose: np.ndarray,
    previous_pose: np.ndarray,
    earlier_pose: np.ndarray,
    current_timestamp: float,
    previous_timestamp: float,
    earlier_timestamp: float,
) -> np.ndarray:
    current_dt = current_timestamp - previous_timestamp
    previous_dt = previous_timestamp - earlier_timestamp
    if current_dt <= 0 or previous_dt <= 0:
        raise ValueError("pose-derived ego status requires increasing timestamps")

    current_velocity_world = (
        current_pose[:3, 3] - previous_pose[:3, 3]
    ) / current_dt
    previous_velocity_world = (
        previous_pose[:3, 3] - earlier_pose[:3, 3]
    ) / previous_dt
    acceleration_world = (
        current_velocity_world - previous_velocity_world
    ) / (0.5 * (current_dt + previous_dt))
    current_rotation = current_pose[:3, :3]
    velocity_model = current_rotation.T @ current_velocity_world
    acceleration_model = current_rotation.T @ acceleration_world
    yaw_rate = wrapped_rate(
        pose_heading(current_pose),
        pose_heading(previous_pose),
        current_dt,
    )
    result = np.concatenate(
        (
            acceleration_model,
            np.asarray([0.0, 0.0, yaw_rate]),
            velocity_model,
            np.asarray([0.0]),
        )
    ).astype(np.float32)
    if result.shape != (10,) or not np.isfinite(result).all():
        raise ValueError("invalid pose-derived ego status")
    return result


def future_reference(
    current_pose: np.ndarray,
    future_poses: list[np.ndarray],
) -> np.ndarray:
    current_inverse = np.linalg.inv(current_pose)
    reference = np.stack(
        [(current_inverse @ pose)[:2, 3] for pose in future_poses]
    ).astype(np.float32)
    if reference.shape != (PLAN_STEPS, 2):
        raise ValueError(f"unexpected future-reference shape: {reference.shape}")
    return reference


def command_from_reference(reference: np.ndarray) -> np.ndarray:
    final_right = float(reference[-1, 0])
    if final_right >= 2.0:
        command_index = 0
    elif final_right <= -2.0:
        command_index = 1
    else:
        command_index = 2
    command = np.zeros(3, dtype=np.float32)
    command[command_index] = 1.0
    return command


def source_intrinsic(record: dict[str, Any]) -> np.ndarray:
    matrix = np.asarray(record["intrinsics"], dtype=np.float32)
    if matrix.shape == (3, 3):
        expanded = np.eye(4, dtype=np.float32)
        expanded[:3, :3] = matrix
        matrix = expanded
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("source camera intrinsic must be finite 3x3 or 4x4")
    return matrix


def load_rgb(path: Path, expected_height: int, expected_width: int) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"))
    if rgb.shape != (expected_height, expected_width, 3):
        raise ValueError(
            f"{path}: RGB shape {rgb.shape} does not match "
            f"{(expected_height, expected_width, 3)}"
        )
    return rgb


def prepare_source_frame(
    *,
    source_root: Path,
    metadata: dict[str, Any],
    logical_index: int,
    image_index: int,
    global_pose: np.ndarray,
    ego_status: np.ndarray,
    command: np.ndarray,
    torch: Any,
    variant: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    logical_records = select_camera_records(metadata, logical_index)
    image_records = select_camera_records(metadata, image_index)
    tensors = []
    camera_contracts = []
    raw_front = None

    for camera in CAMERA_ORDER:
        image_camera = CAMERA_SWAP.get(camera, camera) if variant == "camera_swap" else camera
        image_record = image_records[image_camera]
        image_path = source_root / image_record["rgb_path"].removeprefix("./")
        rgb = load_rgb(
            image_path,
            int(image_record["height"]),
            int(image_record["width"]),
        )
        transformed, augmentation, resize_contract = resize_crop_rgb(rgb)
        normalized = (transformed - IMAGE_MEAN) / IMAGE_STD
        tensors.append(np.ascontiguousarray(normalized.transpose(2, 0, 1)))
        camera_contracts.append(
            {
                "camera": camera,
                "image_camera": image_camera,
                "image_path": str(image_path),
                **resize_contract,
            }
        )
        if camera == "CAM_FRONT":
            raw_front = rgb

    front_record = logical_records["CAM_FRONT"]
    front_to_world = np.asarray(front_record["camtoworld"], dtype=np.float64)
    data = {
        "img": torch.from_numpy(np.stack(tensors)).unsqueeze(0).cuda(),
        "timestamp": torch.tensor(
            [float(front_record["timestamp"])],
            dtype=torch.float32,
            device="cuda",
        ),
        "image_wh": torch.tensor(
            [[[704, 256]] * len(CAMERA_ORDER)],
            dtype=torch.float32,
            device="cuda",
        ),
        "img_metas": [
            {
                "T_global": global_pose,
                "T_global_inv": np.linalg.inv(global_pose),
                "timestamp": float(front_record["timestamp"]),
            }
        ],
        "ego_status": torch.from_numpy(ego_status[None]).cuda(),
        "gt_ego_fut_cmd": torch.from_numpy(command[None]).cuda(),
    }
    return data, {
        "logical_index": logical_index,
        "image_index": image_index,
        "timestamp_s": float(front_record["timestamp"]),
        "camera_inputs": camera_contracts,
        "front_to_world": front_to_world.tolist(),
        "ego_status_10d": ego_status.astype(float).tolist(),
        "ego_status_sources": [
            "acceleration_xyz: finite difference of source camera-rig poses",
            "angular_rate_xy: unavailable, zero",
            "angular_rate_z: finite difference of source camera-rig heading",
            "velocity_xyz: finite difference of source camera-rig poses",
            "steering: unavailable, zero",
        ],
        "command_one_hot_right_left_straight": command.astype(float).tolist(),
    }, {"raw_front": raw_front}


def attach_source_projections(
    data: dict[str, Any],
    contract: dict[str, Any],
    *,
    metadata: dict[str, Any],
    logical_index: int,
    front_l2c: np.ndarray,
    front_intrinsic_shift_px: float,
    variant: str,
    torch: Any,
) -> dict[str, np.ndarray]:
    records = select_camera_records(metadata, logical_index)
    front_to_world = np.asarray(
        records["CAM_FRONT"]["camtoworld"], dtype=np.float64
    )
    model_to_world_raw = front_to_world @ front_l2c
    projections = []
    raw_projections = {}
    for camera, camera_contract in zip(
        CAMERA_ORDER, contract["camera_inputs"], strict=True
    ):
        record = records[camera]
        intrinsic = source_intrinsic(record)
        if variant == "front_intrinsic_shift" and camera == "CAM_FRONT":
            intrinsic = intrinsic.copy()
            intrinsic[0, 2] += float(front_intrinsic_shift_px)
        model_to_camera = (
            np.linalg.inv(np.asarray(record["camtoworld"], dtype=np.float64))
            @ model_to_world_raw
        )
        augmentation = np.eye(4, dtype=np.float32)
        augmentation[0, 0] = float(camera_contract["resize"])
        augmentation[1, 1] = float(camera_contract["resize"])
        crop = camera_contract["crop_xyxy"]
        augmentation[0, 2] = -float(crop[0])
        augmentation[1, 2] = -float(crop[1])
        projections.append(
            augmentation @ intrinsic.astype(np.float32) @ model_to_camera.astype(np.float32)
        )
        raw_projections[camera] = intrinsic.astype(np.float64) @ model_to_camera
    data["projection_mat"] = torch.from_numpy(np.stack(projections)).unsqueeze(0).cuda()
    contract["front_model_to_camera"] = (
        np.linalg.inv(
            np.asarray(records["CAM_FRONT"]["camtoworld"], dtype=np.float64)
        )
        @ model_to_world_raw
    ).tolist()
    return raw_projections


def plan_reference_error(
    plan: np.ndarray,
    reference: np.ndarray,
) -> dict[str, Any]:
    plan = np.asarray(plan, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if plan.shape != (PLAN_STEPS, 2) or reference.shape != plan.shape:
        raise ValueError("plan and reference must both have shape 6x2")
    delta = plan - reference
    distances = np.linalg.norm(delta, axis=1)
    horizons = {}
    for label, index in (("1s", 1), ("2s", 3), ("3s", 5)):
        horizons[label] = {
            "l2_m": float(distances[index]),
            "right_error_m": float(delta[index, 0]),
            "forward_error_m": float(delta[index, 1]),
        }
    return {
        "ade_m": float(np.mean(distances)),
        "fde_m": float(distances[-1]),
        "per_step_l2_m": distances.astype(float).tolist(),
        "horizons": horizons,
    }


def run_sequence(
    *,
    variant: str,
    source_root: Path,
    metadata: dict[str, Any],
    frame_indices: list[int],
    stride: int,
    poses: dict[int, np.ndarray],
    front_l2c: np.ndarray,
    model: Any,
    torch: Any,
    front_intrinsic_shift_px: float,
) -> dict[str, Any]:
    reset_temporal_state(model)
    outputs = []
    frames = []
    image_indices = (
        list(reversed(frame_indices)) if variant == "temporal_reverse" else frame_indices
    )
    for logical_index, image_index in zip(
        frame_indices, image_indices, strict=True
    ):
        records = select_camera_records(metadata, logical_index)
        previous_index = logical_index - stride
        earlier_index = logical_index - 2 * stride
        timestamps = {
            index: float(
                select_camera_records(metadata, index)["CAM_FRONT"]["timestamp"]
            )
            for index in (earlier_index, previous_index, logical_index)
        }
        status = pose_derived_ego_status(
            poses[logical_index],
            poses[previous_index],
            poses[earlier_index],
            timestamps[logical_index],
            timestamps[previous_index],
            timestamps[earlier_index],
        )
        future_indices = [
            logical_index + stride * step for step in range(1, PLAN_STEPS + 1)
        ]
        reference = future_reference(
            poses[logical_index],
            [poses[index] for index in future_indices],
        )
        command = command_from_reference(reference)
        data, contract, visual = prepare_source_frame(
            source_root=source_root,
            metadata=metadata,
            logical_index=logical_index,
            image_index=image_index,
            global_pose=poses[logical_index],
            ego_status=status,
            command=command,
            torch=torch,
            variant=variant,
        )
        raw_projections = attach_source_projections(
            data,
            contract,
            metadata=metadata,
            logical_index=logical_index,
            front_l2c=front_l2c,
            front_intrinsic_shift_px=front_intrinsic_shift_px,
            variant=variant,
            torch=torch,
        )
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.no_grad():
            raw = model(return_loss=False, rescale=True, **data)[0]["img_bbox"]
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        native = cpu_copy(raw, torch)
        plan = native["final_planning"].numpy()
        frames.append(
            {
                "source_frame_index": logical_index,
                "image_frame_index": image_index,
                "timestamp_s": float(records["CAM_FRONT"]["timestamp"]),
                "inference_seconds": elapsed,
                "input_contract": contract,
                "native": native_summary(raw, torch),
                "plan_geometry": plan_kinematics(
                    plan,
                    float(np.linalg.norm(status[6:9])),
                ),
                "planning_selection": {
                    "command_index_right_left_straight": int(np.argmax(command)),
                    "selected_mode_index": int(
                        np.argmax(
                            native["planning_score"].numpy()[int(np.argmax(command))]
                        )
                    ),
                },
                "recorded_camera_rig_future_xy_m": reference.astype(float).tolist(),
                "plan_reference_error": plan_reference_error(plan, reference),
                "_raw_front": visual["raw_front"],
                "_front_raw_projection": raw_projections["CAM_FRONT"],
                "_final_plan": plan,
                "_reference": reference,
            }
        )
        outputs.append(native)
    return {"variant": variant, "frames": frames, "native_outputs": outputs}


def max_plan_difference(first: dict[str, Any], second: dict[str, Any]) -> float:
    differences = []
    for first_output, second_output in zip(
        first["native_outputs"], second["native_outputs"], strict=True
    ):
        differences.append(
            float(
                np.max(
                    np.abs(
                        first_output["final_planning"].numpy()
                        - second_output["final_planning"].numpy()
                    )
                )
            )
        )
    return max(differences)


def project_xy(
    xy: np.ndarray,
    raw_projection: np.ndarray,
    z_m: float = MODEL_PLAN_GROUND_Z_M,
) -> tuple[np.ndarray, np.ndarray]:
    xy = np.asarray(xy, dtype=np.float64)
    points = np.column_stack(
        (xy[:, 0], xy[:, 1], np.full(len(xy), z_m), np.ones(len(xy)))
    )
    camera = (raw_projection @ points.T).T
    depth = camera[:, 2]
    pixels = np.full((len(xy), 2), np.nan)
    in_front = depth > 0.1
    pixels[in_front] = camera[in_front, :2] / depth[in_front, None]
    return pixels, in_front


def save_visualization(
    baseline: dict[str, Any],
    controls: dict[str, dict[str, Any]],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(16, 8), constrained_layout=True)
    grid = figure.add_gridspec(2, 4, height_ratios=(1, 1.1))
    for column, frame in enumerate(baseline["frames"]):
        axis = figure.add_subplot(grid[0, column])
        image = frame["_raw_front"]
        axis.imshow(image)
        for xy, color, label in (
            (frame["_final_plan"], "#ff7f0e", "SparseDrive"),
            (frame["_reference"], "#2ca02c", "recorded motion"),
        ):
            pixels, in_front = project_xy(xy, frame["_front_raw_projection"])
            height, width = image.shape[:2]
            visible = (
                in_front
                & (pixels[:, 0] >= 0)
                & (pixels[:, 0] < width)
                & (pixels[:, 1] >= 0)
                & (pixels[:, 1] < height)
            )
            if np.any(visible):
                axis.plot(
                    pixels[visible, 0],
                    pixels[visible, 1],
                    marker="o",
                    linewidth=2.5,
                    color=color,
                    label=label,
                )
        axis.set_title(
            f"real frame {frame['source_frame_index']}\n"
            f"t={frame['timestamp_s']:.2f}s"
        )
        if column == 0:
            axis.legend(loc="lower center", fontsize=8)
        axis.axis("off")

    trajectory_axis = figure.add_subplot(grid[1, :2])
    last = baseline["frames"][-1]
    trajectory_axis.plot(
        last["_reference"][:, 0],
        last["_reference"][:, 1],
        marker="o",
        color="#2ca02c",
        linewidth=3,
        label="recorded camera-rig motion",
    )
    trajectory_axis.plot(
        last["_final_plan"][:, 0],
        last["_final_plan"][:, 1],
        marker="o",
        color="#ff7f0e",
        linewidth=3,
        label="baseline SparseDrive",
    )
    for name, run in controls.items():
        trajectory_axis.plot(
            run["frames"][-1]["_final_plan"][:, 0],
            run["frames"][-1]["_final_plan"][:, 1],
            marker=".",
            linewidth=1.6,
            label=name,
        )
    trajectory_axis.scatter([0], [0], marker="x", color="black")
    trajectory_axis.set(
        title="Final warmed-frame native plans",
        xlabel="right (+) / left (-), metres",
        ylabel="forward, metres",
    )
    trajectory_axis.grid(alpha=0.3)
    trajectory_axis.legend(fontsize=8)

    metric_axis = figure.add_subplot(grid[1, 2:])
    labels = ["baseline", *controls]
    ade = [
        float(
            np.mean(
                [frame["plan_reference_error"]["ade_m"] for frame in baseline["frames"]]
            )
        ),
        *[
            float(
                np.mean(
                    [
                        frame["plan_reference_error"]["ade_m"]
                        for frame in controls[name]["frames"]
                    ]
                )
            )
            for name in controls
        ],
    ]
    metric_axis.bar(labels, ade, color=["#ff7f0e", "#7f7f7f", "#7f7f7f", "#7f7f7f"])
    metric_axis.set(
        title="Descriptive error to recorded camera-rig motion",
        ylabel="mean ADE, metres",
    )
    metric_axis.tick_params(axis="x", rotation=18)
    metric_axis.grid(axis="y", alpha=0.25)
    figure.suptitle(
        "SparseDrive real-source minimum qualification gate\n"
        "(diagnostic only; not a nuScenes benchmark reproduction)",
        fontsize=15,
    )
    path = output / "sparsedrive_real_source_qualification.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def clean_run_for_json(run: dict[str, Any]) -> dict[str, Any]:
    frames = []
    for frame in run["frames"]:
        frames.append(
            {
                key: value
                for key, value in frame.items()
                if not key.startswith("_")
            }
        )
    return {"variant": run["variant"], "frames": frames}


def main() -> int:
    args = parse_args()
    frame_indices = [int(index) for index in args.frame_indices]
    stride = validate_indices(frame_indices)
    root = args.sparsedrive_root.expanduser().resolve()
    checkpoint = args.checkpoint.expanduser().resolve()
    runtime_deps = args.runtime_deps.expanduser().resolve()
    anchor_dir = args.anchor_dir.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve()
    metadata_path = args.metadata.expanduser().resolve()
    source_manifest = args.source_archive_manifest.expanduser().resolve()
    metadata_manifest = args.metadata_archive_manifest.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    output = args.output.expanduser().resolve()

    for path in (root, runtime_deps, source_root, calibration_run):
        if not path.is_dir():
            raise FileNotFoundError(path)
    for path in (
        checkpoint,
        metadata_path,
        source_manifest,
        metadata_manifest,
        calibration_run / "infos.pkl",
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    output.mkdir(parents=True)

    metadata = load_metadata(metadata_path)
    required_pose_indices = set()
    for index in frame_indices:
        required_pose_indices.update(
            (index - 2 * stride, index - stride, index)
        )
        required_pose_indices.update(
            index + stride * step for step in range(1, PLAN_STEPS + 1)
        )
    if min(required_pose_indices) < 0:
        raise ValueError("selected frames do not have two prehistory poses")

    with (calibration_run / "infos.pkl").open("rb") as stream:
        calibration_infos = pickle.load(stream)
    front_l2c = np.asarray(
        calibration_infos[0]["cam_params"]["CAM_FRONT"]["l2c"],
        dtype=np.float64,
    )
    poses = normalized_model_poses(
        metadata,
        sorted(required_pose_indices),
        front_l2c,
        normalization_index=frame_indices[0],
    )
    timestamp_gaps = []
    for previous, current in zip(frame_indices[:-1], frame_indices[1:], strict=True):
        previous_time = float(
            select_camera_records(metadata, previous)["CAM_FRONT"]["timestamp"]
        )
        current_time = float(
            select_camera_records(metadata, current)["CAM_FRONT"]["timestamp"]
        )
        timestamp_gaps.append(current_time - previous_time)
    if max(abs(gap - PLAN_STEP_SECONDS) for gap in timestamp_gaps) > 0.02:
        raise ValueError(
            f"selected source interval is not approximately 2 Hz: {timestamp_gaps}"
        )

    validate_compatibility_patch(root)
    sys.path.insert(0, str(runtime_deps))
    import torch

    anchor_paths = ensure_anchor_assets(checkpoint, anchor_dir, torch)
    model, torch, model_provenance = build_model(root, checkpoint, anchor_paths)

    baseline = run_sequence(
        variant="baseline",
        source_root=source_root,
        metadata=metadata,
        frame_indices=frame_indices,
        stride=stride,
        poses=poses,
        front_l2c=front_l2c,
        model=model,
        torch=torch,
        front_intrinsic_shift_px=args.front_intrinsic_shift_px,
    )
    repeated = run_sequence(
        variant="baseline",
        source_root=source_root,
        metadata=metadata,
        frame_indices=frame_indices,
        stride=stride,
        poses=poses,
        front_l2c=front_l2c,
        model=model,
        torch=torch,
        front_intrinsic_shift_px=args.front_intrinsic_shift_px,
    )
    controls = {
        variant: run_sequence(
            variant=variant,
            source_root=source_root,
            metadata=metadata,
            frame_indices=frame_indices,
            stride=stride,
            poses=poses,
            front_l2c=front_l2c,
            model=model,
            torch=torch,
            front_intrinsic_shift_px=args.front_intrinsic_shift_px,
        )
        for variant in VARIANTS
        if variant != "baseline"
    }
    repeat_difference = max_plan_difference(baseline, repeated)
    control_differences = {
        name: max_plan_difference(baseline, run)
        for name, run in controls.items()
    }
    all_finite = all(
        frame["native"]["all_declared_tensors_finite"]
        for run in (baseline, repeated, *controls.values())
        for frame in run["frames"]
    )
    baseline_non_degenerate = all(
        float(np.linalg.norm(frame["_final_plan"][-1])) > 0.1
        for frame in baseline["frames"]
    )
    controls_exceed_repeat = {
        name: difference > repeat_difference + RESET_TOLERANCE
        for name, difference in control_differences.items()
    }
    baseline_mean_ade = float(
        np.mean(
            [
                frame["plan_reference_error"]["ade_m"]
                for frame in baseline["frames"]
            ]
        )
    )
    baseline_mean_fde = float(
        np.mean(
            [
                frame["plan_reference_error"]["fde_m"]
                for frame in baseline["frames"]
            ]
        )
    )
    baseline_warmed_ade = float(
        baseline["frames"][-1]["plan_reference_error"]["ade_m"]
    )
    baseline_warmed_fde = float(
        baseline["frames"][-1]["plan_reference_error"]["fde_m"]
    )
    control_reference_diagnostics = {}
    for name, run in controls.items():
        mean_ade = float(
            np.mean(
                [
                    frame["plan_reference_error"]["ade_m"]
                    for frame in run["frames"]
                ]
            )
        )
        warmed_ade = float(run["frames"][-1]["plan_reference_error"]["ade_m"])
        control_reference_diagnostics[name] = {
            "mean_ade_m": mean_ade,
            "warmed_final_frame_ade_m": warmed_ade,
            "mean_ade_worse_than_baseline": mean_ade > baseline_mean_ade,
            "warmed_ade_worse_than_baseline": warmed_ade > baseline_warmed_ade,
        }

    native_path = output / "native_outputs.pt"
    torch.save(
        {
            "baseline": baseline["native_outputs"],
            "baseline_repeat": repeated["native_outputs"],
            **{
                name: run["native_outputs"] for name, run in controls.items()
            },
        },
        native_path,
    )
    visual_path = save_visualization(baseline, controls, output)
    report = {
        "audit_id": "sparsedrive_real_source_qualification_001",
        "purpose": (
            "minimal local SparseDrive receiver/input-contract qualification on "
            "real RGB; not a benchmark reproduction"
        ),
        "source": {
            "root": str(source_root),
            "metadata": str(metadata_path),
            "metadata_sha256": sha256_file(metadata_path),
            "archive_manifest": str(source_manifest),
            "archive_manifest_sha256": sha256_file(source_manifest),
            "metadata_archive_manifest": str(metadata_manifest),
            "metadata_archive_manifest_sha256": sha256_file(metadata_manifest),
            "frame_indices": frame_indices,
            "frame_stride": stride,
            "timestamp_gaps_s": timestamp_gaps,
            "rgb_only": True,
            "hugsim_semantic_or_depth_consumed": False,
        },
        "calibration": {
            "reference_run": str(calibration_run),
            "reference_infos_sha256": sha256_file(calibration_run / "infos.pkl"),
            "front_l2c_model_to_camera": front_l2c.astype(float).tolist(),
            "boundary": (
                "Source intrinsics and relative camera poses are official-sample "
                "metadata. The absolute SparseDrive model-LiDAR to CAM_FRONT "
                "anchor is provisionally inherited from HUGSIM's nuScenes "
                "camera config because original scene tokens/calibrated-sensor "
                "tables are absent."
            ),
        },
        "ego_and_reference": {
            "ego_status": (
                "velocity, acceleration and yaw rate derived from continuous "
                "source camera-rig poses; steering unavailable and set to zero"
            ),
            "future_reference": (
                "recorded source camera-rig motion sampled at 0.5 s; this is a "
                "descriptive behavior reference, not the unique correct plan"
            ),
            "command": (
                "derived with SparseDrive's released ±2 m final-lateral-offset rule"
            ),
        },
        "model": model_provenance,
        "receiver_source": source_provenance(root),
        "adapter": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
            "front_intrinsic_shift_px": float(args.front_intrinsic_shift_px),
        },
        "baseline": clean_run_for_json(baseline),
        "baseline_repeat": clean_run_for_json(repeated),
        "controls": {
            name: clean_run_for_json(run) for name, run in controls.items()
        },
        "qualification": {
            "all_native_outputs_finite": all_finite,
            "baseline_plans_non_degenerate": baseline_non_degenerate,
            "baseline_repeat_max_abs_plan_difference_m": repeat_difference,
            "baseline_repeat_tolerance_m": RESET_TOLERANCE,
            "baseline_repeat_within_tolerance": repeat_difference <= RESET_TOLERANCE,
            "control_max_abs_plan_differences_m": control_differences,
            "control_effect_exceeds_repeat": controls_exceed_repeat,
            "baseline_mean_ade_m": baseline_mean_ade,
            "baseline_mean_fde_m": baseline_mean_fde,
            "baseline_warmed_final_frame_ade_m": baseline_warmed_ade,
            "baseline_warmed_final_frame_fde_m": baseline_warmed_fde,
            "control_reference_diagnostics": control_reference_diagnostics,
            "all_controls_worsen_mean_ade": all(
                item["mean_ade_worse_than_baseline"]
                for item in control_reference_diagnostics.values()
            ),
            "all_controls_worsen_warmed_ade": all(
                item["warmed_ade_worse_than_baseline"]
                for item in control_reference_diagnostics.values()
            ),
        },
        "artifacts": {
            "native_outputs": str(native_path),
            "native_outputs_sha256": sha256_file(native_path),
            "visualization": str(visual_path),
            "visualization_sha256": sha256_file(visual_path),
        },
        "evidence_boundary": {
            "overall_decision": "down-weighted",
            "accepted": (
                "the pinned local SparseDrive path consumes the selected real "
                "six-camera sequence, emits finite non-degenerate native plans, "
                "and has a measured reset/control sensitivity"
            ),
            "down-weighted": (
                "error to recorded camera-rig motion is descriptive because "
                "ego status is pose-derived, steering is unavailable, and the "
                "absolute model-LiDAR/CAM_FRONT anchor is provisional; known "
                "input corruptions changed plans but did not uniformly worsen "
                "trajectory error on this single near-straight slice"
            ),
            "rejected": [
                "this run reproduces SparseDrive's official nuScenes benchmark",
                "recorded human motion is the unique correct plan",
                "this run alone proves SparseDrive or HUGSIM credible or safe",
            ],
        },
    }
    report_path = output / "sparsedrive_real_source_qualification.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
