#!/usr/bin/env python3
"""Audit the frozen SparseDrive-plan to HUGSIM-loop capability handoff."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from hugsim_control_adapter import exact_control_hold_steps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-output", required=True, type=Path)
    parser.add_argument("--native-index", required=True, type=int)
    parser.add_argument("--source-infos", required=True, type=Path)
    parser.add_argument("--source-frame-index", required=True, type=int)
    parser.add_argument("--kinematic", required=True, type=Path)
    parser.add_argument("--run-a", required=True, type=Path)
    parser.add_argument("--run-b", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def initial_state_matches(
    source_info: dict[str, Any],
    run_info: dict[str, Any],
) -> tuple[bool, float]:
    fields = ("ego_box", "ego_pos", "ego_rot", "ego_velo", "ego_steer")
    residuals = [
        float(
            np.max(
                np.abs(
                    np.asarray(source_info[field], dtype=np.float64)
                    - np.asarray(run_info[field], dtype=np.float64)
                )
            )
        )
        for field in fields
    ]
    maximum = max(residuals)
    return maximum <= 1e-12, maximum


def kinematic_residuals(
    steps: list[dict[str, Any]],
    environment_timestep_s: float,
) -> dict[str, float]:
    velocity = []
    steering = []
    for step in steps:
        before = step["info_before"]
        after = step["info_after"]
        action = step["action"]
        velocity.append(
            abs(
                float(after["ego_velo"])
                - (
                    float(before["ego_velo"])
                    + float(action["acc"]) * environment_timestep_s
                )
            )
        )
        steering.append(
            abs(
                float(after["ego_steer"])
                - (
                    float(before["ego_steer"])
                    + float(action["steer_rate"])
                    * environment_timestep_s
                )
            )
        )
    return {
        "maximum_velocity_update_residual": max(velocity),
        "maximum_steering_update_residual": max(steering),
    }


def analyze_contract(
    native_plan: np.ndarray,
    source_info: dict[str, Any],
    run_a: dict[str, Any],
    writer_a: dict[str, Any],
    run_b: dict[str, Any],
    writer_b: dict[str, Any],
    environment_timestep_s: float,
) -> dict[str, Any]:
    steps_a = run_a["steps"]
    steps_b = run_b["steps"]
    expected_hold = exact_control_hold_steps(0.5, environment_timestep_s)
    state_match, state_residual = initial_state_matches(
        source_info,
        steps_a[0]["info_before"],
    )
    runtime_plan = np.asarray(steps_a[0]["plan_traj"], dtype=np.float64)
    plan_identity = np.array_equal(
        np.asarray(native_plan, dtype=np.float64),
        runtime_plan,
    )
    actions_held = len(steps_a) == expected_hold and all(
        step["action"] == steps_a[0]["action"] for step in steps_a
    )
    cadence_pattern = [
        bool(step["plan_updated"]) for step in steps_a
    ] == [True, False] and [
        int(step["control_hold_substep"]) for step in steps_a
    ] == [0, 1]
    writer_gate = all(
        (
            writer["status"] == "complete"
            and writer["responses_sent"] == 1
            and writer["done_received"]
            and not writer["exhausted_without_done"]
            and not writer["padding_or_repetition_used"]
        )
        for writer in (writer_a, writer_b)
    )
    run_gate = all(
        (
            run["run_status"] == "complete"
            and run["completed_steps"] == expected_hold
            and run["plan_updates_consumed"] == 1
            and run["control_hold_steps"] == expected_hold
            and run["strict_action_bounds"]
            and run["evaluation_skipped"]
            and run["control_convention"] == "corrected"
        )
        for run in (run_a, run_b)
    )
    exact_reset = steps_a == steps_b and writer_a == writer_b
    residuals = kinematic_residuals(steps_a, environment_timestep_s)
    kinematic_gate = max(residuals.values()) <= 1e-12
    no_termination = all(
        not step["terminated"]
        and not step["truncated"]
        and not step["info_after"]["collision"]
        for step in steps_a
    )
    gates = {
        "source_state_exactly_recreated": state_match,
        "native_plan_identity_preserved": plan_identity,
        "half_second_plan_to_two_quarter_second_steps": cadence_pattern,
        "one_control_action_held_without_plan_repetition": actions_held,
        "writer_completed_without_padding_or_exhaustion": writer_gate,
        "runner_contract_and_action_bounds_passed": run_gate,
        "kinematic_updates_match_declared_actions": kinematic_gate,
        "independent_reset_is_exact": exact_reset,
        "no_termination_or_collision_in_capability_window": no_termination,
    }
    decision = "accepted" if all(gates.values()) else "rejected"
    return {
        "audit_id": "hugsim_sparsedrive_plan_to_loop_001",
        "role": "plan-interface capability; frozen replay is not a live AD agent",
        "environment_timestep_s": environment_timestep_s,
        "sparsedrive_and_ilqr_timestep_s": 0.5,
        "expected_control_hold_steps": expected_hold,
        "source_state_maximum_abs_residual": state_residual,
        "native_plan_right_forward_m": runtime_plan.tolist(),
        "action": steps_a[0]["action"],
        "speed_mps": [
            float(steps_a[0]["info_before"]["ego_velo"]),
            *[float(step["info_after"]["ego_velo"]) for step in steps_a],
        ],
        "kinematic_residuals": residuals,
        "gates": gates,
        "evidence_decisions": {
            "frozen_plan_to_loop_capability": {
                "decision": decision,
                "claim": (
                    "one fully warmed native SparseDrive plan crossed the "
                    "audited HUGSIM FIFO/controller boundary and produced "
                    "the declared bounded state update reproducibly"
                ),
            },
            "live_ad_closed_loop_response": {
                "decision": "rejected",
                "reason": "the replay writer does not infer from returned observations",
            },
            "real_world_closed_loop_credibility": {
                "decision": "rejected",
                "reason": "scope exceeds this simulator-internal capability gate",
            },
        },
    }


def save_visualization(analysis: dict[str, Any], output: Path) -> Path:
    import matplotlib.pyplot as plt

    plan = np.asarray(analysis["native_plan_right_forward_m"])
    speed = analysis["speed_mps"]
    action = analysis["action"]
    figure, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)

    axes[0].plot(
        np.r_[0.0, plan[:, 0]],
        np.r_[0.0, plan[:, 1]],
        marker="o",
    )
    axes[0].set(
        title="Native plan passed unchanged",
        xlabel="right, m",
        ylabel="forward, m",
    )
    axes[1].plot((0.0, 0.25, 0.5), speed, marker="o")
    axes[1].set(
        title="HUGSIM speed over two substeps",
        xlabel="loop time, s",
        ylabel="speed, m/s",
    )
    axes[2].bar(
        ("acceleration", "steer rate"),
        (action["acc"], action["steer_rate"]),
    )
    axes[2].set(
        title="One held controller action",
        ylabel="m/s² or rad/s",
    )
    for axis in axes:
        axis.grid(alpha=0.3)
    figure.suptitle("SparseDrive plan → HUGSIM loop capability gate")
    path = output / "plan_to_loop_capability.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    native = torch.load(
        args.native_output.expanduser().resolve(),
        map_location="cpu",
        weights_only=False,
    )
    native_plan = native[args.native_index]["final_planning"].numpy()
    with args.source_infos.expanduser().resolve().open("rb") as stream:
        source_info = pickle.load(stream)[args.source_frame_index]
    kinematic = yaml.safe_load(
        args.kinematic.expanduser().resolve().read_text()
    )
    run_dirs = [
        args.run_a.expanduser().resolve(),
        args.run_b.expanduser().resolve(),
    ]
    runs = [load_json(path / "audit_summary.json") for path in run_dirs]
    writers = [
        load_json(path / "sparsedrive_plan_replay_summary.json")
        for path in run_dirs
    ]
    analysis = analyze_contract(
        native_plan,
        source_info,
        runs[0],
        writers[0],
        runs[1],
        writers[1],
        float(kinematic["dt"]),
    )
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    visual = save_visualization(analysis, output)
    analysis["runs"] = [str(path) for path in run_dirs]
    analysis["visualization"] = str(visual)
    report = output / "plan_to_loop_audit.json"
    report.write_text(json.dumps(analysis, indent=2) + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
