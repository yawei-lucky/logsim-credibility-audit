#!/usr/bin/env python3
"""Run a bounded SparseDrive Stage2 smoke sequence on recorded HUGSIM RGB.

This is a receiver/runtime qualification tool, not a credibility score. It
uses only the six RGB cameras and their calibration, preserves SparseDrive's
native outputs, and records the provisional input-contract assumptions that
must be qualified before planning responses are interpreted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from run_sparse4d_hugsim_receiver import parse_runs, prepare_frame, sha256_file


ANCHOR_KEYS = {
    "kmeans_det_900.npy": "head.det_head.instance_bank.anchor",
    "kmeans_map_100.npy": "head.map_head.instance_bank.anchor",
    "kmeans_motion_6.npy": "head.motion_plan_head.motion_anchor",
    "kmeans_plan_6.npy": "head.motion_plan_head.plan_anchor",
}
EXPECTED_ANCHOR_SHAPES = {
    "kmeans_det_900.npy": (900, 11),
    "kmeans_map_100.npy": (100, 40),
    "kmeans_motion_6.npy": (10, 6, 12, 2),
    "kmeans_plan_6.npy": (3, 6, 6, 2),
}
NATIVE_TENSOR_KEYS = (
    "boxes_3d",
    "scores_3d",
    "labels_3d",
    "cls_scores",
    "instance_ids",
    "trajs_3d",
    "trajs_score",
    "anchor_queue",
    "period",
    "planning_score",
    "planning",
    "final_planning",
    "ego_period",
    "ego_anchor_queue",
)
RESET_TOLERANCE = 1e-4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sparsedrive-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--runtime-deps",
        type=Path,
        required=True,
        help="Isolated pip --target directory containing prettytable and einops.",
    )
    parser.add_argument(
        "--anchor-dir",
        type=Path,
        required=True,
        help="Persistent directory for anchors extracted from the official checkpoint.",
    )
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help="Recorded HUGSIM run; repeat for multiple independent conditions.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=2,
        help="Default 2 converts HUGSIM 4 Hz records to SparseDrive's 2 Hz interval.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=4,
        help="Bounded receiver frames per condition.",
    )
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def command_vector(info: dict[str, Any]) -> np.ndarray:
    command = int(info["command"])
    if command not in (0, 1, 2):
        raise ValueError(f"unsupported HUGSIM command: {command}")
    vector = np.zeros(3, dtype=np.float32)
    vector[command] = 1.0
    return vector


def wrapped_rate(current: float, previous: float, dt: float) -> float:
    if dt <= 0:
        raise ValueError(f"timestamps must increase, got dt={dt}")
    delta = math.atan2(math.sin(current - previous), math.cos(current - previous))
    return delta / dt


def ego_status_vector(
    info: dict[str, Any],
    previous_info: dict[str, Any] | None,
) -> np.ndarray:
    """Map available HUGSIM state to SparseDrive's 10-D CAN-bus contract.

    The mapping is provisional: longitudinal acceleration and velocity occupy
    the first component of their respective xyz triples, yaw rate is derived
    from consecutive ego-box headings, and unavailable components are zero.
    """

    yaw_rate = 0.0
    if previous_info is not None:
        dt = float(info["timestamp"]) - float(previous_info["timestamp"])
        yaw_rate = wrapped_rate(
            float(np.asarray(info["ego_box"])[6]),
            float(np.asarray(previous_info["ego_box"])[6]),
            dt,
        )
    status = np.asarray(
        [
            float(info["accelerate"]),
            0.0,
            0.0,
            0.0,
            0.0,
            yaw_rate,
            float(info["ego_velo"]),
            0.0,
            0.0,
            float(info["ego_steer"]),
        ],
        dtype=np.float32,
    )
    if not np.isfinite(status).all():
        raise ValueError("non-finite HUGSIM ego state")
    return status


def ensure_anchor_assets(checkpoint: Path, anchor_dir: Path, torch: Any) -> dict[str, str]:
    anchor_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: anchor_dir / name for name in ANCHOR_KEYS}
    valid = all(
        path.is_file() and np.load(path).shape == EXPECTED_ANCHOR_SHAPES[name]
        for name, path in paths.items()
    )
    if not valid:
        checkpoint_data = torch.load(checkpoint, map_location="cpu")
        state_dict = checkpoint_data["state_dict"]
        for name, key in ANCHOR_KEYS.items():
            value = state_dict[key].detach().cpu().numpy()
            if value.shape != EXPECTED_ANCHOR_SHAPES[name]:
                raise ValueError(f"{key}: unexpected shape {value.shape}")
            np.save(paths[name], value)
        del checkpoint_data
    return {name: str(path.resolve()) for name, path in paths.items()}


def git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def source_provenance(root: Path) -> dict[str, Any]:
    diff = git_output(root, "diff", "--binary")
    return {
        "root": str(root),
        "commit": git_output(root, "rev-parse", "HEAD").strip(),
        "status": git_output(root, "status", "--short").splitlines(),
        "working_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
    }


def validate_compatibility_patch(root: Path) -> None:
    required_markers = {
        root / "projects/mmdet3d_plugin/models/attention.py": "class TorchMHA",
        root / "projects/mmdet3d_plugin/models/motion/instance_queue.py": (
            "feature_map = feature_maps[-1][:, 0]"
        ),
        root / "projects/mmdet3d_plugin/ops/__init__.py": (
            "deformable_aggregation_ext is unavailable"
        ),
    }
    for path, marker in required_markers.items():
        if not path.is_file() or marker not in path.read_text():
            raise RuntimeError(
                f"SparseDrive compatibility patch is absent from {path}; "
                "apply third_party_patches/sparsedrive_pytorch_fallback.patch"
            )


def build_model(
    root: Path,
    checkpoint: Path,
    anchor_paths: dict[str, str],
) -> tuple[Any, Any, dict[str, Any]]:
    os.chdir(root)
    sys.path.insert(0, str(root))
    import torch
    from mmcv import Config
    from mmcv.runner import load_checkpoint
    from mmdet.models import build_detector

    import projects.mmdet3d_plugin  # noqa: F401

    config_path = root / "projects/configs/sparsedrive_small_stage2.py"
    cfg = Config.fromfile(str(config_path))
    cfg.model["use_deformable_func"] = False
    cfg.model["img_backbone"]["pretrained"] = None
    cfg.model["head"]["det_head"]["deformable_model"]["use_deformable_func"] = False
    cfg.model["head"]["map_head"]["deformable_model"]["use_deformable_func"] = False
    cfg.model["head"]["det_head"]["instance_bank"]["anchor"] = anchor_paths[
        "kmeans_det_900.npy"
    ]
    cfg.model["head"]["map_head"]["instance_bank"]["anchor"] = anchor_paths[
        "kmeans_map_100.npy"
    ]
    cfg.model["head"]["motion_plan_head"]["motion_anchor"] = anchor_paths[
        "kmeans_motion_6.npy"
    ]
    cfg.model["head"]["motion_plan_head"]["plan_anchor"] = anchor_paths[
        "kmeans_plan_6.npy"
    ]

    model = build_detector(cfg.model)
    load_checkpoint(model, str(checkpoint), map_location="cpu", strict=True)
    model.cuda().eval()
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    provenance = {
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "attention_implementation": type(model.head.det_head.layers[4].attn).__name__,
        "custom_deformable_cuda_enabled": False,
    }
    return model, torch, provenance


def reset_temporal_state(model: Any) -> None:
    model.head.det_head.instance_bank.reset()
    model.head.map_head.instance_bank.reset()
    model.head.motion_plan_head.instance_queue.reset()


def prepare_sparsedrive_frame(
    observation: dict[str, Any],
    info: dict[str, Any],
    previous_info: dict[str, Any] | None,
    torch: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = prepare_frame(observation, info, torch)
    input_contract = data.pop("input_contract")
    status = ego_status_vector(info, previous_info)
    command = command_vector(info)
    data["ego_status"] = torch.from_numpy(status[None]).cuda()
    data["gt_ego_fut_cmd"] = torch.from_numpy(command[None]).cuda()
    contract = {
        "cameras": input_contract,
        "camera_order": [item["camera"] for item in input_contract],
        "timestamp_s": float(info["timestamp"]),
        "ego_status_10d": status.astype(float).tolist(),
        "command_one_hot_right_left_straight": command.astype(float).tolist(),
        "reference_frame": (
            "provisional virtual LiDAR frame coincident with the HUGSIM vehicle "
            "frame used by the existing Sparse4D adapter"
        ),
    }
    return data, contract


def tensor_summary(value: Any, torch: Any) -> dict[str, Any]:
    if torch.is_tensor(value):
        finite = bool(torch.isfinite(value).all()) if value.is_floating_point() else True
        return {
            "type": "tensor",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "finite": finite,
        }
    if isinstance(value, np.ndarray):
        finite = bool(np.isfinite(value).all()) if np.issubdtype(value.dtype, np.number) else True
        return {
            "type": "ndarray",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "finite": finite,
        }
    return {"type": type(value).__name__}


def native_summary(result: dict[str, Any], torch: Any) -> dict[str, Any]:
    summary = {
        key: tensor_summary(result[key], torch)
        for key in NATIVE_TENSOR_KEYS
        if key in result
    }
    scores = result["scores_3d"].detach().cpu().numpy()
    labels = result["labels_3d"].detach().cpu().numpy()
    boxes = result["boxes_3d"].detach().cpu().numpy()
    top = min(10, len(scores))
    summary["top_detections"] = [
        {
            "rank": index,
            "label_id": int(labels[index]),
            "score": float(scores[index]),
            "box": boxes[index].astype(float).tolist(),
        }
        for index in range(top)
    ]
    summary["all_declared_tensors_finite"] = all(
        item.get("finite", True)
        for key, item in summary.items()
        if key in NATIVE_TENSOR_KEYS
    )
    summary["planning_score_values"] = (
        result["planning_score"].detach().cpu().numpy().astype(float).tolist()
    )
    summary["final_planning_values"] = (
        result["final_planning"].detach().cpu().numpy().astype(float).tolist()
    )
    return summary


def cpu_copy(value: Any, torch: Any) -> Any:
    if torch.is_tensor(value):
        return value.detach().cpu()
    if isinstance(value, dict):
        return {key: cpu_copy(item, torch) for key, item in value.items()}
    if isinstance(value, list):
        return [cpu_copy(item, torch) for item in value]
    if isinstance(value, tuple):
        return tuple(cpu_copy(item, torch) for item in value)
    return value


def max_abs_difference(first: Any, second: Any, torch: Any) -> float:
    a = first.detach().cpu().float()
    b = second.detach().cpu().float()
    if a.shape != b.shape:
        return math.inf
    return float(torch.max(torch.abs(a - b))) if a.numel() else 0.0


def save_runtime_visualization(
    label: str,
    indices: list[int],
    observations: list[dict[str, Any]],
    infos: list[dict[str, Any]],
    native_outputs: list[dict[str, Any]],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(4 * len(indices), 7), constrained_layout=True)
    grid = figure.add_gridspec(2, len(indices), height_ratios=(1, 1.15))
    for position, frame_index in enumerate(indices):
        axis = figure.add_subplot(grid[0, position])
        axis.imshow(np.asarray(observations[frame_index]["rgb"]["CAM_FRONT"]))
        axis.set_title(f"frame {frame_index}, t={float(infos[frame_index]['timestamp']):.1f}s")
        axis.axis("off")

    plan_axis = figure.add_subplot(grid[1, :])
    for frame_index, info_row, native in zip(
        indices, (infos[index] for index in indices), native_outputs, strict=True
    ):
        plan = native["final_planning"].numpy()
        plan_axis.plot(
            plan[:, 0],
            plan[:, 1],
            marker="o",
            label=f"frame {frame_index}, t={float(info_row['timestamp']):.1f}s",
        )
    plan_axis.scatter([0], [0], color="black", marker="x", label="ego origin")
    plan_axis.set(
        title="SparseDrive native final plans (model axes remain provisionally mapped)",
        xlabel="model trajectory axis 0",
        ylabel="model trajectory axis 1",
    )
    plan_axis.grid(alpha=0.3)
    plan_axis.legend()
    figure.suptitle(
        "SparseDrive runtime smoke: CAM_FRONT inputs and native final plans",
        fontsize=15,
    )
    path = output / f"{label}_runtime_smoke.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def run_condition(
    label: str,
    run_path: Path,
    model: Any,
    torch: Any,
    frame_stride: int,
    max_frames: int,
    output: Path,
) -> dict[str, Any]:
    observations = load_pickle(run_path / "observations.pkl")
    infos = load_pickle(run_path / "infos.pkl")
    if len(observations) != len(infos):
        raise ValueError(f"{label}: observation/info length mismatch")
    indices = list(range(0, len(infos), frame_stride))[:max_frames]
    if not indices:
        raise ValueError(f"{label}: no selected frames")

    reset_temporal_state(model)
    native_outputs = []
    frames = []
    previous_info = None
    first_data = None
    first_native = None
    contracts = []
    for frame_index in indices:
        data, contract = prepare_sparsedrive_frame(
            observations[frame_index],
            infos[frame_index],
            previous_info,
            torch,
        )
        if first_data is None:
            first_data, _ = prepare_sparsedrive_frame(
                observations[frame_index],
                infos[frame_index],
                None,
                torch,
            )
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.no_grad():
            raw = model(return_loss=False, rescale=True, **data)[0]["img_bbox"]
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        native = cpu_copy(raw, torch)
        if first_native is None:
            first_native = native
        native_outputs.append(native)
        frames.append(
            {
                "frame_index": frame_index,
                "timestamp_s": float(infos[frame_index]["timestamp"]),
                "inference_seconds": elapsed,
                "native": native_summary(raw, torch),
            }
        )
        contracts.append(contract)
        previous_info = infos[frame_index]

    reset_temporal_state(model)
    with torch.no_grad():
        repeated = model(return_loss=False, rescale=True, **first_data)[0]["img_bbox"]
    reset_differences = {
        key: max_abs_difference(first_native[key], repeated[key], torch)
        for key in ("scores_3d", "planning_score", "final_planning")
    }
    reset_reproducible = all(
        value <= RESET_TOLERANCE for value in reset_differences.values()
    )

    native_path = output / f"{label}_native_outputs.pt"
    torch.save(native_outputs, native_path)
    visualization_path = save_runtime_visualization(
        label,
        indices,
        observations,
        infos,
        native_outputs,
        output,
    )
    return {
        "label": label,
        "input": str(run_path),
        "selected_frame_indices": indices,
        "frame_count": len(indices),
        "frames": frames,
        "input_contracts": contracts,
        "reset_check": {
            "max_abs_differences": reset_differences,
            "tolerance": RESET_TOLERANCE,
            "reproducible": reset_reproducible,
        },
        "native_output": str(native_path),
        "native_output_sha256": sha256_file(native_path),
        "visualization": str(visualization_path),
        "visualization_sha256": sha256_file(visualization_path),
    }


def main() -> int:
    args = parse_args()
    if args.frame_stride < 1:
        raise ValueError("--frame-stride must be at least 1")
    if args.max_frames < 1:
        raise ValueError("--max-frames must be at least 1")

    root = args.sparsedrive_root.expanduser().resolve()
    checkpoint = args.checkpoint.expanduser().resolve()
    runtime_deps = args.runtime_deps.expanduser().resolve()
    anchor_dir = args.anchor_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    if not runtime_deps.is_dir():
        raise FileNotFoundError(runtime_deps)
    validate_compatibility_patch(root)
    output.mkdir(parents=True, exist_ok=False)

    sys.path.insert(0, str(runtime_deps))
    import torch

    runs = parse_runs(args.run)
    anchor_paths = ensure_anchor_assets(checkpoint, anchor_dir, torch)
    model, torch, model_provenance = build_model(root, checkpoint, anchor_paths)
    runner_path = Path(__file__).resolve()
    patch_path = (
        runner_path.parents[1]
        / "third_party_patches"
        / "sparsedrive_pytorch_fallback.patch"
    )
    report = {
        "experiment": "sparsedrive_hugsim_runtime_smoke_001",
        "purpose": "runtime and provisional input-contract qualification only",
        "source": source_provenance(root),
        "runtime_dependencies": {
            "root": str(runtime_deps),
            "prettytable_version": __import__("prettytable").__version__,
            "einops_version": __import__("einops").__version__,
        },
        "model": model_provenance,
        "adapter": {
            "runner": str(runner_path),
            "runner_sha256": sha256_file(runner_path),
            "compatibility_patch": str(patch_path),
            "compatibility_patch_sha256": sha256_file(patch_path),
        },
        "anchor_paths": anchor_paths,
        "frame_stride": args.frame_stride,
        "max_frames": args.max_frames,
        "conditions": [],
        "evidence_boundary": {
            "status": "down-weighted",
            "allowed": (
                "the official SparseDrive checkpoint loads strictly and emits "
                "finite native outputs on a bounded HUGSIM RGB sequence"
            ),
            "not_allowed": [
                "the provisional virtual-LiDAR/ego frame is correct",
                "the 10-D ego-status adaptation is externally valid",
                "the SparseDrive planning response is credible",
                "HUGSIM is equivalent to reality",
            ],
        },
    }
    for label, run_path in runs:
        report["conditions"].append(
            run_condition(
                label,
                run_path,
                model,
                torch,
                args.frame_stride,
                args.max_frames,
                output,
            )
        )
    report["all_outputs_finite"] = all(
        frame["native"]["all_declared_tensors_finite"]
        for condition in report["conditions"]
        for frame in condition["frames"]
    )
    report["all_resets_reproducible"] = all(
        condition["reset_check"]["reproducible"] for condition in report["conditions"]
    )
    report_path = output / "runtime_smoke.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
