#!/usr/bin/env python3
"""Replay frozen SparseDrive plans through HUGSIM's FIFO capability boundary.

This is an interface qualification tool, not a live AD agent.  It ignores the
new observation content and sends selected, previously generated native plans
without padding, truncation, interpolation, or final-plan repetition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import Any

import torch

from hugsim_control_adapter import sparsedrive_plan_to_hugsim_lidar_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--native-output", required=True, type=Path)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-plans", type=int, required=True)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wait_for_fifo(path: Path, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for FIFO: {path}")


def load_plans(path: Path, start_index: int, max_plans: int) -> list[Any]:
    if start_index < 0:
        raise ValueError("--start-index must be non-negative")
    if max_plans < 1:
        raise ValueError("--max-plans must be at least 1")
    native = torch.load(path, map_location="cpu", weights_only=False)
    selected = native[start_index : start_index + max_plans]
    if len(selected) != max_plans:
        raise ValueError(
            f"requested {max_plans} plans from index {start_index}, "
            f"but source contains only {len(native)}"
        )
    return [
        sparsedrive_plan_to_hugsim_lidar_plan(
            item["final_planning"].detach().cpu().numpy()
        )
        for item in selected
    ]


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    native_output = args.native_output.expanduser().resolve()
    if not native_output.is_file():
        raise FileNotFoundError(native_output)
    plans = load_plans(
        native_output,
        args.start_index,
        args.max_plans,
    )
    obs_pipe = output / "obs_pipe"
    plan_pipe = output / "plan_pipe"
    wait_for_fifo(obs_pipe, args.timeout_s)
    wait_for_fifo(plan_pipe, args.timeout_s)

    sent: list[dict[str, Any]] = []
    done_received = False
    exhausted_without_done = False
    while True:
        with obs_pipe.open("rb") as pipe:
            payload = pickle.loads(pipe.read())
        if payload == "Done":
            done_received = True
            break
        _, info = payload
        if len(sent) >= len(plans):
            with plan_pipe.open("wb") as pipe:
                pipe.write(pickle.dumps(None))
            exhausted_without_done = True
            break
        plan = plans[len(sent)]
        with plan_pipe.open("wb") as pipe:
            pipe.write(pickle.dumps(plan))
        sent.append(
            {
                "source_index": args.start_index + len(sent),
                "receiver_timestamp_s": float(info["timestamp"]),
                "waypoint_count": len(plan),
                "first_waypoint_right_forward_m": plan[0].tolist(),
                "last_waypoint_right_forward_m": plan[-1].tolist(),
            }
        )

    summary = {
        "status": (
            "complete"
            if done_received and len(sent) == len(plans)
            else "incomplete"
        ),
        "role": "frozen SparseDrive plan replay; not a live AD agent",
        "native_output": str(native_output),
        "native_output_sha256": sha256(native_output),
        "source_timestep_s": 0.5,
        "hugsim_plan_axes": "[right, forward] metres",
        "start_index": args.start_index,
        "requested_plans": args.max_plans,
        "responses_sent": len(sent),
        "done_received": done_received,
        "exhausted_without_done": exhausted_without_done,
        "padding_or_repetition_used": False,
        "plans": sent,
    }
    with (output / "sparsedrive_plan_replay_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(summary, stream, indent=2)
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
