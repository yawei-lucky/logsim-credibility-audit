#!/usr/bin/env python3
"""Run frozen SparseDrive on live HUGSIM FIFO observations at 2 Hz.

The model is reset and pre-warmed with three exact recorded frames.  HUGSIM is
started from the matching fourth-frame vehicle state.  Every returned live
observation then produces a new native plan; no plan is repeated or padded.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from hugsim_control_adapter import sparsedrive_plan_to_hugsim_lidar_plan
from run_sparsedrive_hugsim_receiver import (
    build_model,
    cpu_copy,
    ensure_anchor_assets,
    git_output,
    native_summary,
    plan_kinematics,
    prepare_sparsedrive_frame,
    reset_temporal_state,
    sha256_file,
    source_provenance,
    validate_compatibility_patch,
)


PREWARM_INDICES = (0, 2, 4)
BOUNDARY_INDEX = 6
SOURCE_FRAME_STRIDE = 2
SOURCE_TIMESTEP_S = 0.5
INITIAL_HISTORY_FIELDS = ("accelerate", "steer_rate")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--reference-native-output", required=True, type=Path)
    parser.add_argument("--reference-native-index", type=int, default=3)
    parser.add_argument("--max-plans", type=int, required=True)
    parser.add_argument("--sparsedrive-root", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--runtime-deps", required=True, type=Path)
    parser.add_argument("--anchor-dir", required=True, type=Path)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


def wait_for_fifo(path: Path, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for FIFO: {path}")


def adjusted_live_info(
    live_info: dict[str, Any],
    boundary_info: dict[str, Any],
    *,
    first_live_frame: bool,
) -> dict[str, Any]:
    adjusted = copy.deepcopy(live_info)
    adjusted["timestamp"] = float(boundary_info["timestamp"]) + float(
        live_info["timestamp"]
    )
    if first_live_frame:
        for field in INITIAL_HISTORY_FIELDS:
            adjusted[field] = boundary_info[field]
    return adjusted


def maximum_boundary_state_residual(
    live_info: dict[str, Any],
    boundary_info: dict[str, Any],
) -> float:
    fields = ("ego_box", "ego_pos", "ego_rot", "ego_velo", "ego_steer")
    return max(
        float(
            np.max(
                np.abs(
                    np.asarray(live_info[field], dtype=np.float64)
                    - np.asarray(boundary_info[field], dtype=np.float64)
                )
            )
        )
        for field in fields
    )


def rgb_maximum_difference(
    live_observation: dict[str, Any],
    source_observation: dict[str, Any],
) -> int:
    return max(
        int(
            np.max(
                np.abs(
                    live_observation["rgb"][camera].astype(np.int16)
                    - source_observation["rgb"][camera].astype(np.int16)
                )
            )
        )
        for camera in source_observation["rgb"]
    )


def rgb_digest(observation: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for camera in sorted(observation["rgb"]):
        digest.update(camera.encode())
        digest.update(np.ascontiguousarray(observation["rgb"][camera]).tobytes())
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    if args.max_plans < 1:
        raise ValueError("--max-plans must be at least 1")
    output = args.output.expanduser().resolve()
    source_run = args.source_run.expanduser().resolve()
    reference_native_path = args.reference_native_output.expanduser().resolve()
    root = args.sparsedrive_root.expanduser().resolve()
    checkpoint = args.checkpoint.expanduser().resolve()
    runtime_deps = args.runtime_deps.expanduser().resolve()
    anchor_dir = args.anchor_dir.expanduser().resolve()
    for path in (source_run, root, runtime_deps):
        if not path.is_dir():
            raise FileNotFoundError(path)
    for path in (reference_native_path, checkpoint):
        if not path.is_file():
            raise FileNotFoundError(path)

    observations = load_pickle(source_run / "observations.pkl")
    infos = load_pickle(source_run / "infos.pkl")
    expected_timestamps = [0.0, 0.5, 1.0, 1.5]
    actual_timestamps = [
        float(infos[index]["timestamp"])
        for index in (*PREWARM_INDICES, BOUNDARY_INDEX)
    ]
    if not np.allclose(actual_timestamps, expected_timestamps, atol=1e-12):
        raise ValueError(f"unexpected prewarm timestamps: {actual_timestamps}")

    sys.path.insert(0, str(runtime_deps))
    import torch

    validate_compatibility_patch(root)
    anchors = ensure_anchor_assets(checkpoint, anchor_dir, torch)
    model, torch, model_provenance = build_model(
        root,
        checkpoint,
        anchors,
    )
    reset_temporal_state(model)

    prewarm_records = []
    native_outputs = []
    previous_info = None
    for index in PREWARM_INDICES:
        data, contract = prepare_sparsedrive_frame(
            observations[index],
            infos[index],
            previous_info,
            torch,
            ego_status_mode="recorded_scalar",
        )
        with torch.no_grad():
            raw = model(return_loss=False, rescale=True, **data)[0]["img_bbox"]
        prewarm_records.append(
            {
                "source_index": index,
                "timestamp_s": float(infos[index]["timestamp"]),
                "input_contract": contract,
                "native": native_summary(raw, torch),
            }
        )
        previous_info = infos[index]

    reference_native = torch.load(
        reference_native_path,
        map_location="cpu",
        weights_only=False,
    )[args.reference_native_index]["final_planning"].numpy()
    boundary_info = infos[BOUNDARY_INDEX]
    boundary_observation = observations[BOUNDARY_INDEX]
    obs_pipe = output / "obs_pipe"
    plan_pipe = output / "plan_pipe"
    wait_for_fifo(obs_pipe, args.timeout_s)
    wait_for_fifo(plan_pipe, args.timeout_s)

    live_records = []
    done_received = False
    exhausted_without_done = False
    first_plan_reference_delta = None
    while True:
        with obs_pipe.open("rb") as pipe:
            payload = pickle.loads(pipe.read())
        if payload == "Done":
            done_received = True
            break
        observation, live_info = payload
        if len(live_records) >= args.max_plans:
            with plan_pipe.open("wb") as pipe:
                pipe.write(pickle.dumps(None))
            exhausted_without_done = True
            break

        first_live_frame = len(live_records) == 0
        adjusted_info = adjusted_live_info(
            live_info,
            boundary_info,
            first_live_frame=first_live_frame,
        )
        if first_live_frame:
            state_residual = maximum_boundary_state_residual(
                live_info,
                boundary_info,
            )
            rgb_residual = rgb_maximum_difference(
                observation,
                boundary_observation,
            )
            if state_residual > 1e-12 or rgb_residual != 0:
                raise ValueError(
                    "live boundary differs from recorded warm-up boundary: "
                    f"state={state_residual}, rgb={rgb_residual}"
                )

        data, contract = prepare_sparsedrive_frame(
            observation,
            adjusted_info,
            previous_info,
            torch,
            ego_status_mode="recorded_scalar",
        )
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.no_grad():
            raw = model(return_loss=False, rescale=True, **data)[0]["img_bbox"]
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        plan = sparsedrive_plan_to_hugsim_lidar_plan(
            raw["final_planning"].detach().cpu().numpy()
        )
        if first_live_frame:
            first_plan_reference_delta = float(
                np.max(np.abs(plan - reference_native))
            )
            if first_plan_reference_delta > 1e-4:
                raise ValueError(
                    "first live plan exceeds qualified reset envelope: "
                    f"{first_plan_reference_delta}"
                )
        with plan_pipe.open("wb") as pipe:
            pipe.write(pickle.dumps(plan))

        native_outputs.append(cpu_copy(raw, torch))
        live_records.append(
            {
                "plan_index": len(live_records),
                "environment_timestamp_s": float(live_info["timestamp"]),
                "receiver_timestamp_s": float(adjusted_info["timestamp"]),
                "observation_rgb_sha256": rgb_digest(observation),
                "inference_seconds": elapsed,
                "input_contract": contract,
                "native": native_summary(raw, torch),
                "plan_geometry": plan_kinematics(
                    plan,
                    float(adjusted_info["ego_velo"]),
                ),
            }
        )
        previous_info = adjusted_info

    native_output_path = output / "sparsedrive_live_native_outputs.pt"
    torch.save(native_outputs, native_output_path)
    repo = Path(__file__).resolve().parents[1]
    summary = {
        "status": (
            "complete"
            if done_received and len(live_records) == args.max_plans
            else "incomplete"
        ),
        "role": "frozen SparseDrive live receiver; open-loop plans drive HUGSIM iLQR",
        "source_run": str(source_run),
        "source_input_sha256": {
            name: sha256_file(source_run / name)
            for name in ("observations.pkl", "infos.pkl")
        },
        "prewarm_indices": list(PREWARM_INDICES),
        "boundary_index": BOUNDARY_INDEX,
        "receiver_timestamp_offset_s": float(boundary_info["timestamp"]),
        "initial_history_fields_from_boundary": list(INITIAL_HISTORY_FIELDS),
        "first_live_boundary_state_max_abs_residual": 0.0,
        "first_live_boundary_rgb_max_abs_difference": 0,
        "first_plan_reference_native": str(reference_native_path),
        "first_plan_reference_index": args.reference_native_index,
        "first_plan_reference_max_abs_difference": first_plan_reference_delta,
        "reset_numerical_envelope": 1e-4,
        "model": model_provenance,
        "source": source_provenance(root),
        "writer": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "audit_repo_commit": git_output(repo, "rev-parse", "HEAD").strip(),
            "audit_repo_status": git_output(
                repo,
                "status",
                "--short",
            ).splitlines(),
        },
        "requested_plans": args.max_plans,
        "plans_sent": len(live_records),
        "done_received": done_received,
        "exhausted_without_done": exhausted_without_done,
        "padding_or_repetition_used": False,
        "prewarm": prewarm_records,
        "live": live_records,
        "native_output": str(native_output_path),
        "native_output_sha256": sha256_file(native_output_path),
    }
    with (output / "sparsedrive_live_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(summary, stream, indent=2)
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
