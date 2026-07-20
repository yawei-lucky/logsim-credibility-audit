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
import hashlib
import json
import pickle
import subprocess
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def build_forward_plan(horizon: int, step_m: float, lateral_m: float = 0.0) -> np.ndarray:
    """Build a simple forward plan in local coordinates.

    HUGSIM documents the planned trajectory in lidar coordinates: x to right,
    y to forward, z upward. We therefore keep x nearly constant and increase y.
    The audit runner's corrected control adapter converts this convention to the
    iLQR controller frame before calculating both positions and heading.
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
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help=(
            "Maximum planner responses to send. The writer keeps listening "
            "after the limit so it can receive the simulator's Done signal."
        ),
    )
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    obs_pipe = output / "obs_pipe"
    plan_pipe = output / "plan_pipe"

    wait_for_fifo(obs_pipe, args.timeout_s)
    wait_for_fifo(plan_pipe, args.timeout_s)

    print(f"[plan-pipe-writer] using obs_pipe={obs_pipe}")
    print(f"[plan-pipe-writer] using plan_pipe={plan_pipe}")

    plan = build_forward_plan(args.horizon, args.step_m, args.lateral_m)

    responses_sent = 0
    done_received = False
    while True:
        with open(obs_pipe, "rb") as pipe:
            payload = pickle.loads(pipe.read())

        if payload == "Done":
            print("[plan-pipe-writer] simulator signaled Done")
            done_received = True
            break

        obs, info = payload
        print(
            f"[plan-pipe-writer] step={responses_sent} "
            f"received {describe_info(info)}"
        )

        with open(plan_pipe, "wb") as pipe:
            if responses_sent < args.max_steps:
                pipe.write(pickle.dumps(plan.copy()))
                responses_sent += 1
            else:
                # Unblock a runner that requested more steps than this writer
                # was configured to serve. The runner treats None as an early
                # planner stop and then sends the final Done handshake.
                pipe.write(pickle.dumps(None))
                print(
                    "[plan-pipe-writer] response limit reached; "
                    "sent planner stop and awaiting Done"
                )

    summary = {
        "status": "complete" if done_received else "incomplete",
        "output": str(output),
        "horizon": args.horizon,
        "step_m": args.step_m,
        "lateral_m": args.lateral_m,
        "max_steps": args.max_steps,
        "responses_sent": responses_sent,
        "done_received": done_received,
        "writer_script_sha256": sha256(Path(__file__).resolve()),
        "audit_repo_commit": git_commit(Path(__file__).resolve().parents[1]),
    }
    with (output / "plan_writer_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(summary, stream, indent=2)

    print(
        f"[plan-pipe-writer] finished responses_sent={responses_sent} "
        f"done_received={done_received}"
    )
    return 0 if done_received else 1


if __name__ == "__main__":
    raise SystemExit(main())
