#!/usr/bin/env python3
"""Minimal deterministic HUGSIM plan-pipe writer.

This helper is intended for a Phase 1 smoke test only. It is not an AD model.
It reads `(obs, info)` from HUGSIM's `obs_pipe` and writes a simple forward
trajectory to `plan_pipe` so that the simulator loop can advance without
installing UniAD/VAD/LTF first.

Run in a separate shell after `closed_loop.py` creates the FIFO pipes:

    /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
        scripts/hugsim_plan_pipe_writer.py \
        --output /path/to/hugsim/output/scene-mode

Notes:
- HUGSIM's `closed_loop.py` creates `obs_pipe` and `plan_pipe` under the output directory.
- The plan is in the same 2D local/lidar-style convention consumed by `traj2control`.
- This script is for smoke testing the simulator/audit loop, not for evaluating driving performance.
"""

from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path
from typing import Any

import numpy as np


def wait_for_fifo(path: Path, timeout_s: float) -> None:
    start = time.time()
    while True:
        if path.exists():
            return
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for FIFO: {path}")
        time.sleep(0.25)


def build_forward_plan(horizon: int, step_m: float, lateral_m: float = 0.0) -> np.ndarray:
    """Build a simple forward plan in local coordinates.

    HUGSIM's `traj2control` comment states the planned trajectory is under lidar
    coordinates: x to right, y to forward, z upward. We therefore keep x nearly
    constant and increase y.
    """
    ys = np.arange(1, horizon + 1, dtype=np.float32) * float(step_m)
    xs = np.full_like(ys, float(lateral_m), dtype=np.float32)
    return np.stack([xs, ys], axis=1)


def describe_info(info: dict[str, Any]) -> str:
    timestamp = info.get("timestamp", "?")
    ego_velo = info.get("ego_velo", "?")
    rc = info.get("rc", "?")
    collision = info.get("collision", "?")
    return f"timestamp={timestamp}, ego_velo={ego_velo}, rc={rc}, collision={collision}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write deterministic trajectories to HUGSIM plan_pipe.")
    parser.add_argument("--output", required=True, help="HUGSIM output directory containing obs_pipe and plan_pipe.")
    parser.add_argument("--horizon", type=int, default=6, help="Number of planned 2D waypoints.")
    parser.add_argument("--step-m", type=float, default=1.0, help="Forward distance between waypoints in meters.")
    parser.add_argument("--lateral-m", type=float, default=0.0, help="Constant lateral offset in meters.")
    parser.add_argument("--timeout-s", type=float, default=120.0, help="Seconds to wait for FIFO creation.")
    parser.add_argument("--max-steps", type=int, default=50, help="Maximum planner responses to send.")
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    obs_pipe = output / "obs_pipe"
    plan_pipe = output / "plan_pipe"

    wait_for_fifo(obs_pipe, args.timeout_s)
    wait_for_fifo(plan_pipe, args.timeout_s)

    print(f"[plan-pipe-writer] using obs_pipe={obs_pipe}")
    print(f"[plan-pipe-writer] using plan_pipe={plan_pipe}")

    plan = build_forward_plan(args.horizon, args.step_m, args.lateral_m)

    for step_idx in range(args.max_steps):
        with open(obs_pipe, "rb") as pipe:
            payload = pickle.loads(pipe.read())

        if payload == "Done":
            print("[plan-pipe-writer] simulator signaled Done")
            break

        obs, info = payload
        print(f"[plan-pipe-writer] step={step_idx} received {describe_info(info)}")

        with open(plan_pipe, "wb") as pipe:
            pipe.write(pickle.dumps(plan.copy()))

    print("[plan-pipe-writer] finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
