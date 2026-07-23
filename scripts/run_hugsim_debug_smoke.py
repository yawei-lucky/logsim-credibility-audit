#!/usr/bin/env python3
"""Run a bounded HUGSIM loop without launching a heavyweight AD client.

This runner preserves HUGSIM's FIFO observation/plan boundary while adding a
bounded step count and audit-oriented outputs. Start this process first, then
run ``scripts/hugsim_plan_pipe_writer.py`` against the same output directory.

The runner intentionally overrides ``model_path`` from the released scene's
``cfg.yaml`` because the released file contains the original author's absolute
path rather than the local extracted asset path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded deterministic HUGSIM smoke loop.")
    parser.add_argument("--hugsim-root", default="/home/yawei/HUGSIM")
    parser.add_argument(
        "--scenario",
        default="/home/yawei/HUGSIM/configs/benchmark/nuscenes/scene-0383-easy-00.yaml",
    )
    parser.add_argument(
        "--base",
        default="/home/yawei/logsim-credibility-audit/configs/hugsim/nuscenes_smoke_base.yaml",
    )
    parser.add_argument(
        "--camera",
        default="/home/yawei/HUGSIM/configs/sim/nuscenes_camera.yaml",
    )
    parser.add_argument(
        "--kinematic",
        default="/home/yawei/HUGSIM/configs/sim/kinematic.yaml",
    )
    parser.add_argument(
        "--output",
        default="/home/yawei/logsim-credibility-audit/artifacts/hugsim_smoke/scene-0383-easy-00",
    )
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument(
        "--control-hold-steps",
        type=int,
        default=1,
        help=(
            "Environment steps that reuse one computed control action. "
            "The plan pipe is read only at the start of each hold interval."
        ),
    )
    parser.add_argument(
        "--strict-action-bounds",
        action="store_true",
        help="Fail instead of passing an out-of-range control to HUGSIM.",
    )
    parser.add_argument(
        "--skip-evaluation",
        action="store_true",
        help="Record loop evidence without running HUGSIM NC/TTC/PDMS scoring.",
    )
    parser.add_argument(
        "--control-convention",
        choices=("corrected", "upstream"),
        default="corrected",
        help=(
            "Coordinate conversion used before iLQR. 'corrected' calculates "
            "heading after converting [right, forward] to [forward, lateral]; "
            "'upstream' reproduces the released HUGSIM traj2control behavior."
        ),
    )
    parser.add_argument(
        "--warm-start-source-run",
        type=Path,
        help=(
            "Replay recorded source actions before opening the live FIFO, "
            "while requiring state and RGB to reproduce the source run."
        ),
    )
    parser.add_argument(
        "--warm-start-steps",
        type=int,
        default=0,
        help="Number of recorded 0.25 s source actions to replay.",
    )
    return parser.parse_args()


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


def maximum_state_residual(
    current: dict[str, Any],
    reference: dict[str, Any],
) -> float:
    fields = (
        "timestamp",
        "ego_box",
        "ego_pos",
        "ego_rot",
        "ego_velo",
        "ego_steer",
        "obj_boxes",
    )
    return max(
        float(
            np.max(
                np.abs(
                    np.asarray(current[field], dtype=np.float64)
                    - np.asarray(reference[field], dtype=np.float64)
                )
            )
        )
        for field in fields
    )


def rgb_maximum_difference(
    current: dict[str, Any],
    reference: dict[str, Any],
) -> int:
    if set(current["rgb"]) != set(reference["rgb"]):
        raise ValueError("warm-start camera membership differs from source")
    return max(
        int(
            np.max(
                np.abs(
                    current["rgb"][camera].astype(np.int16)
                    - reference["rgb"][camera].astype(np.int16)
                )
            )
        )
        for camera in reference["rgb"]
    )


def replay_source_warm_start(
    env: Any,
    observation: dict[str, Any],
    info: dict[str, Any],
    source_run: Path,
    step_count: int,
    *,
    state_atol: float = 1e-8,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_observations = load_pickle(source_run / "observations.pkl")
    source_infos = load_pickle(source_run / "infos.pkl")
    source_steps = load_pickle(source_run / "audit_steps.pkl")
    if step_count < 1:
        raise ValueError("warm-start step count must be at least 1")
    if (
        len(source_observations) <= step_count
        or len(source_infos) <= step_count
        or len(source_steps) < step_count
    ):
        raise ValueError("source run is shorter than requested warm start")

    records = []
    for index in range(step_count + 1):
        state_residual = maximum_state_residual(info, source_infos[index])
        rgb_residual = rgb_maximum_difference(
            observation,
            source_observations[index],
        )
        records.append(
            {
                "source_index": index,
                "timestamp_s": float(info["timestamp"]),
                "state_max_abs_residual": state_residual,
                "rgb_max_abs_difference": rgb_residual,
            }
        )
        if state_residual > state_atol or rgb_residual != 0:
            raise ValueError(
                "warm-start replay differs from source at index "
                f"{index}: state={state_residual}, rgb={rgb_residual}"
            )
        if index == step_count:
            break
        source_step = source_steps[index]
        if int(source_step["step_id"]) != index:
            raise ValueError("source warm-start steps are not contiguous")
        observation, _, terminated, truncated, info = env.step(
            source_step["action"]
        )
        if terminated or truncated:
            raise RuntimeError(
                f"source warm start ended at step {index}"
            )

    return observation, info, {
        "enabled": True,
        "source_run": str(source_run),
        "step_count": step_count,
        "state_atol": state_atol,
        "maximum_state_residual": max(
            item["state_max_abs_residual"] for item in records
        ),
        "maximum_rgb_difference": max(
            item["rgb_max_abs_difference"] for item in records
        ),
        "records": records,
    }


def ensure_fifo(path: Path) -> None:
    if path.exists():
        if not stat.S_ISFIFO(path.stat().st_mode):
            raise RuntimeError(f"Refusing to replace non-FIFO path: {path}")
        path.unlink()
    os.mkfifo(path)


def git_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def git_status(root: Path) -> list[str]:
    status = subprocess.check_output(
        ["git", "-C", str(root), "status", "--short"],
        text=True,
    )
    return status.splitlines()


def vehicle_asset_evidence(
    plan_list: list[list[Any]],
    realcar_root: Path,
) -> list[dict[str, Any]]:
    assets = []
    for actor in plan_list:
        model_id = str(actor[5])
        model_root = realcar_root / model_id
        files = {}
        for filename in ("gs.pth", "wlh.json"):
            path = model_root / filename
            files[filename] = {
                "path": str(path),
                "sha256": sha256(path) if path.is_file() else None,
            }
        assets.append(
            {
                "model_id": model_id,
                "initial_state": {
                    "right_m": actor[0],
                    "forward_m": actor[1],
                    "height_m": actor[2],
                    "yaw_rad": actor[3],
                    "velocity_mps": actor[4],
                },
                "controller": actor[6],
                "controller_args": actor[7],
                "files": files,
            }
        )
    return assets


def make_video(observations: list[dict[str, Any]], output_path: Path) -> None:
    from moviepy import ImageSequenceClip

    frames = []
    for observation in observations:
        rgb = observation["rgb"]
        row1 = np.concatenate(
            [rgb["CAM_FRONT_LEFT"], rgb["CAM_FRONT"], rgb["CAM_FRONT_RIGHT"]],
            axis=1,
        )
        row2 = np.concatenate(
            [rgb["CAM_BACK_RIGHT"], rgb["CAM_BACK"], rgb["CAM_BACK_LEFT"]],
            axis=1,
        )
        frames.append(np.concatenate([row1, row2], axis=0))
    ImageSequenceClip(frames, fps=4).write_videofile(
        str(output_path),
        logger=None,
    )


def build_scoring_frame(
    plan_traj: np.ndarray,
    info_after: dict[str, Any],
    traj_transform_to_global: Any,
) -> dict[str, Any]:
    """Build a metric frame with all state anchored at the same timestamp."""
    imu_plan_traj = plan_traj[:, [1, 0]].copy()
    imu_plan_traj[:, 1] *= -1
    global_traj = traj_transform_to_global(
        imu_plan_traj,
        info_after["ego_box"],
    )
    return {
        "time_stamp": info_after["timestamp"],
        "is_key_frame": True,
        "ego_box": info_after["ego_box"],
        "obj_boxes": info_after["obj_boxes"],
        "obj_names": ["car" for _ in info_after["obj_boxes"]],
        "planned_traj": {"traj": global_traj, "timestep": 0.5},
        "collision": info_after["collision"],
        "rc": info_after["rc"],
    }


def require_action_in_bounds(action: dict[str, float], action_space: Any) -> None:
    for name, value in action.items():
        space = action_space[name]
        scalar = float(value)
        low = float(np.asarray(space.low).reshape(-1)[0])
        high = float(np.asarray(space.high).reshape(-1)[0])
        if not low <= scalar <= high:
            raise ValueError(
                f"{name}={scalar} is outside HUGSIM action bounds [{low}, {high}]"
            )


def main() -> int:
    args = parse_args()
    if args.max_steps < 1:
        raise ValueError("--max-steps must be at least 1")
    if args.control_hold_steps < 1:
        raise ValueError("--control-hold-steps must be at least 1")
    if (args.warm_start_source_run is None) != (args.warm_start_steps == 0):
        raise ValueError(
            "--warm-start-source-run and a positive --warm-start-steps "
            "must be provided together"
        )

    hugsim_root = Path(args.hugsim_root).expanduser().resolve()
    scenario_path = Path(args.scenario).expanduser().resolve()
    base_path = Path(args.base).expanduser().resolve()
    camera_path = Path(args.camera).expanduser().resolve()
    kinematic_path = Path(args.kinematic).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    warm_start_source_run = (
        args.warm_start_source_run.expanduser().resolve()
        if args.warm_start_source_run is not None
        else None
    )
    if (
        warm_start_source_run is not None
        and not warm_start_source_run.is_dir()
    ):
        raise FileNotFoundError(
            f"Missing warm-start source run: {warm_start_source_run}"
        )

    # HUGSIM imports assume its repository root is both cwd and on sys.path.
    os.chdir(hugsim_root)
    sys.path.insert(0, str(hugsim_root))

    import gymnasium
    import hugsim_env  # noqa: F401  # registers the Gym environment
    import open3d as o3d
    from omegaconf import OmegaConf

    from sim.ilqr.lqr import plan2control
    from sim.utils.score_calculator import hugsim_evaluate
    from sim.utils.sim_utils import (
        traj2control as upstream_traj2control,
        traj_transform_to_global,
    )

    from hugsim_control_adapter import corrected_traj2control

    scenario_config = OmegaConf.load(scenario_path)
    base_config = OmegaConf.load(base_path)
    camera_config = OmegaConf.load(camera_path)
    kinematic_config = OmegaConf.load(kinematic_path)
    cfg = OmegaConf.merge(
        {"scenario": scenario_config},
        {"base": base_config},
        {"camera": camera_config},
        {"kinematic": kinematic_config},
    )
    scenario_plan_list = OmegaConf.to_container(
        scenario_config.plan_list,
        resolve=True,
    )
    actor_assets = vehicle_asset_evidence(
        scenario_plan_list,
        Path(base_config.realcar_path).expanduser().resolve(),
    )

    local_model_path = Path(cfg.base.model_base) / cfg.scenario.scene_name
    model_config_path = local_model_path / "cfg.yaml"
    model_config = OmegaConf.load(model_config_path)
    cfg.update(model_config)
    cfg.model_path = str(local_model_path)
    cfg.source_path = str(local_model_path)

    output.mkdir(parents=True, exist_ok=False)
    obs_pipe = output / "obs_pipe"
    plan_pipe = output / "plan_pipe"

    print(f"[debug-smoke] creating environment from {local_model_path}", flush=True)
    env = gymnasium.make("hugsim_env/HUGSim-v0", cfg=cfg, output=str(output))
    obs, info = env.reset()
    warm_start = {"enabled": False}
    if warm_start_source_run is not None:
        obs, info, warm_start = replay_source_warm_start(
            env,
            obs,
            info,
            warm_start_source_run,
            args.warm_start_steps,
        )
        warm_start["source_input_sha256"] = {
            name: sha256(warm_start_source_run / name)
            for name in (
                "observations.pkl",
                "infos.pkl",
                "audit_steps.pkl",
            )
        }
        print(
            "[debug-smoke] warm-start complete "
            f"steps={args.warm_start_steps} timestamp={info['timestamp']}",
            flush=True,
        )

    ensure_fifo(obs_pipe)
    ensure_fifo(plan_pipe)
    print(f"[debug-smoke] ready output={output}", flush=True)

    observations = [obs]
    infos = [info]
    audit_steps: list[dict[str, Any]] = []
    save_data: dict[str, Any] = {"type": "closeloop", "frames": []}
    terminated = False
    truncated = False
    plan_traj: np.ndarray | None = None
    action: dict[str, float] | None = None
    plan_update_id = -1

    for step_id in range(args.max_steps):
        info_before = info
        plan_updated = step_id % args.control_hold_steps == 0
        if plan_updated:
            with obs_pipe.open("wb") as pipe:
                pipe.write(pickle.dumps((obs, info_before)))
            with plan_pipe.open("rb") as pipe:
                plan_traj = pickle.loads(pipe.read())
            if plan_traj is None:
                print("[debug-smoke] planner returned None", flush=True)
                break
            plan_update_id += 1
            if args.control_convention == "corrected":
                acc, steer_rate = corrected_traj2control(
                    plan_traj,
                    info_before,
                    plan2control,
                )
            else:
                acc, steer_rate = upstream_traj2control(plan_traj, info_before)
            action = {"acc": float(acc), "steer_rate": float(steer_rate)}
            if args.strict_action_bounds:
                require_action_in_bounds(action, env.action_space)
        if plan_traj is None or action is None:
            raise RuntimeError("control hold interval started without a plan")
        obs, reward, terminated, truncated, info = env.step(action)

        frame = build_scoring_frame(plan_traj, info, traj_transform_to_global)
        save_data["frames"].append(frame)
        observations.append(obs)
        infos.append(info)
        audit_steps.append(
            {
                "step_id": step_id,
                "plan_updated": plan_updated,
                "plan_update_id": plan_update_id,
                "control_hold_substep": step_id % args.control_hold_steps,
                "info_before": info_before,
                "plan_traj": plan_traj,
                "action": action,
                "reward": reward,
                "terminated": terminated,
                "truncated": truncated,
                "info_after": info,
            }
        )
        print(
            f"[debug-smoke] step={step_id} plan_update={plan_updated} "
            f"timestamp={info['timestamp']} "
            f"rc={info['rc']:.6f} collision={info['collision']} "
            f"acc={float(acc):.6f} steer_rate={float(steer_rate):.6f}",
            flush=True,
        )
        if terminated or truncated:
            break

    # The writer waits for the next observation after returning its last plan.
    with obs_pipe.open("wb") as pipe:
        pipe.write(pickle.dumps("Done"))

    with (output / "data.pkl").open("wb") as stream:
        pickle.dump([save_data], stream)
    with (output / "infos.pkl").open("wb") as stream:
        pickle.dump(infos, stream)
    with (output / "observations.pkl").open("wb") as stream:
        pickle.dump(observations, stream)
    with (output / "audit_steps.pkl").open("wb") as stream:
        pickle.dump(audit_steps, stream)
    make_video(observations, output / "video.mp4")

    eval_result: dict[str, Any] | None = None
    eval_error: str | None = None
    if not args.skip_evaluation:
        try:
            ground_xyz = np.asarray(
                o3d.io.read_point_cloud(str(output / "ground.ply")).points
            )
            scene_xyz = np.asarray(
                o3d.io.read_point_cloud(str(output / "scene.ply")).points
            )
            eval_result = hugsim_evaluate([save_data], ground_xyz, scene_xyz)
            with (output / "eval.json").open("w", encoding="utf-8") as stream:
                json.dump(jsonable(eval_result), stream, indent=2)
        except Exception as exc:  # Keep loop evidence if short-run scoring fails.
            eval_error = f"{type(exc).__name__}: {exc}"
            with (output / "eval_error.txt").open("w", encoding="utf-8") as stream:
                stream.write(eval_error + "\n")

    summary = {
        "run_status": (
            "complete"
            if len(audit_steps) == args.max_steps and eval_error is None
            else "incomplete"
        ),
        "scenario_id": f"{cfg.scenario.scene_name}-{cfg.scenario.mode}",
        "hugsim_commit": git_commit(hugsim_root),
        "hugsim_worktree_status": git_status(hugsim_root),
        "audit_repo": {
            "commit": git_commit(Path(__file__).resolve().parents[1]),
            "worktree_status": git_status(Path(__file__).resolve().parents[1]),
            "runner_script_sha256": sha256(Path(__file__).resolve()),
            "control_adapter_sha256": sha256(
                Path(__file__).resolve().with_name(
                    "hugsim_control_adapter.py"
                )
            ),
        },
        "source_assets": {
            "model_path": str(local_model_path),
            "scenario_yaml": str(scenario_path),
            "scenario_yaml_sha256": sha256(scenario_path),
            "scene_cfg": str(model_config_path),
            "scene_cfg_sha256": sha256(model_config_path),
            "base_yaml": str(base_path),
            "base_yaml_sha256": sha256(base_path),
            "camera_yaml": str(camera_path),
            "camera_yaml_sha256": sha256(camera_path),
            "kinematic_yaml": str(kinematic_path),
            "kinematic_yaml_sha256": sha256(kinematic_path),
            "vehicle_assets": actor_assets,
        },
        "requested_steps": args.max_steps,
        "completed_steps": len(audit_steps),
        "warm_start": warm_start,
        "control_hold_steps": args.control_hold_steps,
        "plan_updates_consumed": sum(
            bool(step["plan_updated"]) for step in audit_steps
        ),
        "strict_action_bounds": args.strict_action_bounds,
        "control_convention": args.control_convention,
        "terminated": terminated,
        "truncated": truncated,
        "observation_modalities": sorted(observations[0].keys()),
        "camera_names": sorted(observations[0]["rgb"].keys()),
        "eval_result": eval_result,
        "eval_error": eval_error,
        "evaluation_skipped": args.skip_evaluation,
        "steps": audit_steps,
    }
    with (output / "audit_summary.json").open("w", encoding="utf-8") as stream:
        json.dump(jsonable(summary), stream, indent=2)

    env.close()
    print(
        f"[debug-smoke] completed_steps={len(audit_steps)} "
        f"eval_status={'skipped' if args.skip_evaluation else ('ok' if eval_error is None else 'error')}",
        flush=True,
    )
    return (
        0
        if len(audit_steps) == args.max_steps and eval_error is None
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
