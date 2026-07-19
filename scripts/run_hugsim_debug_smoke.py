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
        "--control-convention",
        choices=("corrected", "upstream"),
        default="corrected",
        help=(
            "Coordinate conversion used before iLQR. 'corrected' calculates "
            "heading after converting [right, forward] to [forward, lateral]; "
            "'upstream' reproduces the released HUGSIM traj2control behavior."
        ),
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
                    "yaw_deg": actor[3],
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


def main() -> int:
    args = parse_args()
    if args.max_steps < 1:
        raise ValueError("--max-steps must be at least 1")

    hugsim_root = Path(args.hugsim_root).expanduser().resolve()
    scenario_path = Path(args.scenario).expanduser().resolve()
    base_path = Path(args.base).expanduser().resolve()
    camera_path = Path(args.camera).expanduser().resolve()
    kinematic_path = Path(args.kinematic).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

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

    ensure_fifo(obs_pipe)
    ensure_fifo(plan_pipe)
    print(f"[debug-smoke] ready output={output}", flush=True)

    observations = [obs]
    infos = [info]
    audit_steps: list[dict[str, Any]] = []
    save_data: dict[str, Any] = {"type": "closeloop", "frames": []}
    terminated = False
    truncated = False

    for step_id in range(args.max_steps):
        info_before = info
        with obs_pipe.open("wb") as pipe:
            pipe.write(pickle.dumps((obs, info_before)))
        with plan_pipe.open("rb") as pipe:
            plan_traj = pickle.loads(pipe.read())
        if plan_traj is None:
            print("[debug-smoke] planner returned None", flush=True)
            break

        if args.control_convention == "corrected":
            acc, steer_rate = corrected_traj2control(plan_traj, info_before, plan2control)
        else:
            acc, steer_rate = upstream_traj2control(plan_traj, info_before)
        action = {"acc": acc, "steer_rate": steer_rate}
        obs, reward, terminated, truncated, info = env.step(action)

        frame = build_scoring_frame(plan_traj, info, traj_transform_to_global)
        save_data["frames"].append(frame)
        observations.append(obs)
        infos.append(info)
        audit_steps.append(
            {
                "step_id": step_id,
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
            f"[debug-smoke] step={step_id} timestamp={info['timestamp']} "
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
    try:
        ground_xyz = np.asarray(o3d.io.read_point_cloud(str(output / "ground.ply")).points)
        scene_xyz = np.asarray(o3d.io.read_point_cloud(str(output / "scene.ply")).points)
        eval_result = hugsim_evaluate([save_data], ground_xyz, scene_xyz)
        with (output / "eval.json").open("w", encoding="utf-8") as stream:
            json.dump(jsonable(eval_result), stream, indent=2)
    except Exception as exc:  # Keep the smoke evidence even if short-run scoring fails.
        eval_error = f"{type(exc).__name__}: {exc}"
        with (output / "eval_error.txt").open("w", encoding="utf-8") as stream:
            stream.write(eval_error + "\n")

    summary = {
        "scenario_id": f"{cfg.scenario.scene_name}-{cfg.scenario.mode}",
        "hugsim_commit": git_commit(hugsim_root),
        "source_assets": {
            "model_path": str(local_model_path),
            "scenario_yaml": str(scenario_path),
            "scenario_yaml_sha256": sha256(scenario_path),
            "scene_cfg": str(model_config_path),
            "scene_cfg_sha256": sha256(model_config_path),
            "vehicle_assets": actor_assets,
        },
        "requested_steps": args.max_steps,
        "completed_steps": len(audit_steps),
        "control_convention": args.control_convention,
        "terminated": terminated,
        "truncated": truncated,
        "observation_modalities": sorted(observations[0].keys()),
        "camera_names": sorted(observations[0]["rgb"].keys()),
        "eval_result": eval_result,
        "eval_error": eval_error,
        "steps": audit_steps,
    }
    with (output / "audit_summary.json").open("w", encoding="utf-8") as stream:
        json.dump(jsonable(summary), stream, indent=2)

    env.close()
    print(
        f"[debug-smoke] completed_steps={len(audit_steps)} "
        f"eval_status={'ok' if eval_error is None else 'error'}",
        flush=True,
    )
    return 0 if audit_steps else 1


if __name__ == "__main__":
    raise SystemExit(main())
