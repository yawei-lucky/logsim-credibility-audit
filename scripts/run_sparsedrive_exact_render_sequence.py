#!/usr/bin/env python3
"""Run one fixed SparseDrive receiver on preregistered exact-pose renders."""

from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

from render_hugsim_exact_source_pose import CAMERAS, sha256_file
from run_sparsedrive_hugsim_receiver import (
    build_model,
    ensure_anchor_assets,
    source_provenance,
    validate_compatibility_patch,
)
from run_sparsedrive_real_source import (
    PLAN_STEPS,
    RESET_TOLERANCE,
    clean_run_for_json,
    max_plan_difference,
    normalized_model_poses,
    run_sequence,
    validate_indices,
)


def parse_condition_specs(specs: list[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError("--condition must use LABEL=METADATA_PATH")
        label, raw_path = spec.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or label in parsed:
            raise ValueError(f"invalid or duplicate condition label: {label!r}")
        parsed[label] = Path(raw_path).expanduser().resolve()
    if not parsed:
        raise ValueError("at least one condition is required")
    return parsed


def load_render_reports(paths: list[Path], frame_indices: list[int]) -> dict[int, dict[str, Any]]:
    reports: dict[int, dict[str, Any]] = {}
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        frame_index = int(report["frame_index"])
        if frame_index in reports:
            raise ValueError(f"duplicate render report frame: {frame_index}")
        report["_report_path"] = str(path)
        reports[frame_index] = report
    if set(reports) != set(frame_indices):
        raise ValueError("render reports do not exactly match receiver frame indices")
    return reports


def materialize_render_root(
    output: Path,
    label: str,
    metadata_path: Path,
    reports: dict[int, dict[str, Any]],
) -> Path:
    root = output / "input_roots" / label
    metadata_hash = sha256_file(metadata_path)
    for frame_index, report in reports.items():
        if label not in report["variants"]:
            raise ValueError(f"frame {frame_index}: render lacks condition {label}")
        variant = report["variants"][label]
        if variant["metadata_sha256"] != metadata_hash:
            raise ValueError(f"frame {frame_index}: {label} metadata hash mismatch")
        for camera in CAMERAS:
            source = Path(variant["camera_results"][camera]["render_path"]).resolve()
            if not source.is_file() or sha256_file(source) != variant["camera_results"][camera]["render_sha256"]:
                raise ValueError(f"frame {frame_index}: invalid {label}/{camera} render")
            destination = root / "images" / camera / f"{frame_index:05d}.jpg"
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(source, destination)
    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sparsedrive-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--runtime-deps", type=Path, required=True)
    parser.add_argument("--anchor-dir", type=Path, required=True)
    parser.add_argument("--calibration-reference-run", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--condition", action="append", required=True)
    parser.add_argument("--render-report", action="append", type=Path, required=True)
    parser.add_argument("--frame-index", action="append", type=int, required=True, dest="frame_indices")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.sparsedrive_root.expanduser().resolve()
    checkpoint = args.checkpoint.expanduser().resolve()
    runtime_deps = args.runtime_deps.expanduser().resolve()
    anchor_dir = args.anchor_dir.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    preregistration_path = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    frame_indices = [int(value) for value in args.frame_indices]
    stride = validate_indices(frame_indices)
    conditions = parse_condition_specs(args.condition)
    report_paths = [path.expanduser().resolve() for path in args.render_report]
    for path in (root, runtime_deps, calibration_run):
        if not path.is_dir():
            raise FileNotFoundError(path)
    for path in (checkpoint, preregistration_path, calibration_run / "infos.pkl", *conditions.values(), *report_paths):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")

    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    if frame_indices != preregistration["receiver"]["history_source_frames"]:
        raise ValueError("receiver frames differ from preregistration")
    expected_labels = {"factual", *preregistration["conditions"]}
    if set(conditions) != expected_labels:
        raise ValueError("conditions differ from factual plus preregistered labels")
    if sha256_file(checkpoint) != preregistration["receiver"]["checkpoint_sha256"]:
        raise ValueError("SparseDrive checkpoint differs from preregistration")
    for label, spec in preregistration["conditions"].items():
        if sha256_file(conditions[label]) != spec["metadata_sha256"]:
            raise ValueError(f"{label}: metadata differs from preregistration")

    reports = load_render_reports(report_paths, frame_indices)
    output.mkdir(parents=True)
    input_roots = {
        label: materialize_render_root(output, label, metadata_path, reports)
        for label, metadata_path in conditions.items()
    }

    with (calibration_run / "infos.pkl").open("rb") as stream:
        calibration_infos = pickle.load(stream)
    front_l2c = np.asarray(
        calibration_infos[0]["cam_params"]["CAM_FRONT"]["l2c"], dtype=np.float64
    )
    required_pose_indices = set()
    for index in frame_indices:
        required_pose_indices.update((index - 2 * stride, index - stride, index))
        required_pose_indices.update(index + stride * step for step in range(1, PLAN_STEPS + 1))
    if min(required_pose_indices) < 0:
        raise ValueError("selected frames do not have two prehistory poses")

    validate_compatibility_patch(root)
    sys.path.insert(0, str(runtime_deps))
    import torch

    anchor_paths = ensure_anchor_assets(checkpoint, anchor_dir, torch)
    model, torch, model_provenance = build_model(root, checkpoint, anchor_paths)
    runs = {}
    native_outputs = {}
    for label, metadata_path in conditions.items():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        poses = normalized_model_poses(
            metadata,
            sorted(required_pose_indices),
            front_l2c,
            normalization_index=frame_indices[0],
        )
        first = run_sequence(
            variant="baseline",
            source_root=input_roots[label],
            metadata=metadata,
            frame_indices=frame_indices,
            stride=stride,
            poses=poses,
            front_l2c=front_l2c,
            model=model,
            torch=torch,
            front_intrinsic_shift_px=0.0,
        )
        second = run_sequence(
            variant="baseline",
            source_root=input_roots[label],
            metadata=metadata,
            frame_indices=frame_indices,
            stride=stride,
            poses=poses,
            front_l2c=front_l2c,
            model=model,
            torch=torch,
            front_intrinsic_shift_px=0.0,
        )
        repeat_difference = max_plan_difference(first, second)
        runs[label] = {
            "metadata": str(metadata_path),
            "metadata_sha256": sha256_file(metadata_path),
            "replicate_1": clean_run_for_json(first),
            "replicate_2": clean_run_for_json(second),
            "repeat_max_abs_plan_difference_m": repeat_difference,
            "repeat_within_tolerance": repeat_difference <= RESET_TOLERANCE,
            "final_plan_replicate_1_m": first["native_outputs"][-1]["final_planning"].numpy().astype(float).tolist(),
            "final_plan_replicate_2_m": second["native_outputs"][-1]["final_planning"].numpy().astype(float).tolist(),
        }
        native_outputs[label] = {
            "replicate_1": first["native_outputs"],
            "replicate_2": second["native_outputs"],
        }

    native_path = output / "native_outputs.pt"
    torch.save(native_outputs, native_path)
    commands = {
        tuple(run["replicate_1"]["frames"][-1]["input_contract"]["command_one_hot_right_left_straight"])
        for run in runs.values()
    }
    held_fixed_command = len(commands) == 1
    all_repeatable = all(run["repeat_within_tolerance"] for run in runs.values())

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"factual": "#555555", "separated": "#1b9e77", "boundary": "#d95f02", "overlap": "#7570b3"}
    figure, axes = plt.subplots(2, len(conditions), figsize=(4.2 * len(conditions), 7), squeeze=False)
    for column, label in enumerate(conditions):
        front_path = input_roots[label] / "images" / "CAM_FRONT" / f"{frame_indices[-1]:05d}.jpg"
        axes[0, column].imshow(plt.imread(front_path))
        axes[0, column].set_title(f"{label} · CAM_FRONT · frame {frame_indices[-1]}")
        axes[0, column].axis("off")
        plan = np.asarray(runs[label]["final_plan_replicate_1_m"])
        axes[1, column].plot(plan[:, 0], plan[:, 1], marker="o", color=colors.get(label, "#333333"))
        axes[1, column].scatter([0], [0], marker="x", color="black")
        axes[1, column].set_aspect("equal", adjustable="box")
        axes[1, column].set_xlabel("right (m)")
        axes[1, column].set_ylabel("forward (m)")
        axes[1, column].grid(alpha=0.25)
        axes[1, column].set_title("SparseDrive selected 3 s plan")
    figure.suptitle("Preregistered scene-0041 exact-render receiver inputs and outputs")
    figure.tight_layout()
    visualization = output / "sparsedrive_exact_render_sequences.png"
    figure.savefig(visualization, dpi=170)
    plt.close(figure)

    result = {
        "audit_id": "sparsedrive_scene0041_exact_render_sequence_001",
        "preregistration": str(preregistration_path),
        "preregistration_sha256": sha256_file(preregistration_path),
        "frame_indices": frame_indices,
        "render_reports": [
            {"path": str(path), "sha256": sha256_file(path)} for path in report_paths
        ],
        "model": model_provenance,
        "receiver_source": source_provenance(root),
        "calibration_infos": str(calibration_run / "infos.pkl"),
        "calibration_infos_sha256": sha256_file(calibration_run / "infos.pkl"),
        "runs": runs,
        "qualification": {
            "held_fixed_command": held_fixed_command,
            "command_one_hot_right_left_straight": list(next(iter(commands))) if held_fixed_command else None,
            "all_replicates_within_tolerance": all_repeatable,
            "repeat_tolerance_m": RESET_TOLERANCE,
            "all_native_outputs_saved": True,
        },
        "native_outputs": str(native_path),
        "native_outputs_sha256": sha256_file(native_path),
        "visualization": str(visualization),
        "visualization_sha256": sha256_file(visualization),
        "claim_boundary": (
            "This run measures one fixed receiver's output on simulator renders. "
            "It does not make SparseDrive a truth source and does not establish "
            "real-world response correctness, safety or general simulator credibility."
        ),
    }
    report_path = output / "sparsedrive_exact_render_sequence.json"
    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(report_path)
    return 0 if held_fixed_command and all_repeatable else 2


if __name__ == "__main__":
    raise SystemExit(main())
