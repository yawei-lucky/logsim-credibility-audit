#!/usr/bin/env python3
"""Audit short live SparseDrive↔HUGSIM feedback runs and reset sensitivity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True, type=Path)
    parser.add_argument("--run-b", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def plan(record: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        record["native"]["final_planning_values"],
        dtype=np.float64,
    )


def selected_mode(record: dict[str, Any]) -> int:
    scores = np.asarray(
        record["native"]["planning_score_values"],
        dtype=np.float64,
    )
    return int(np.argmax(scores[2]))


def update_steps(runner: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in runner["steps"] if step["plan_updated"]]


def analyze_live_runs(
    runner_a: dict[str, Any],
    writer_a: dict[str, Any],
    runner_b: dict[str, Any],
    writer_b: dict[str, Any],
) -> dict[str, Any]:
    writers = (writer_a, writer_b)
    runners = (runner_a, runner_b)
    requested = writer_a["requested_plans"]
    interface_gate = all(
        (
            writer["status"] == "complete"
            and writer["plans_sent"] == requested
            and writer["done_received"]
            and not writer["exhausted_without_done"]
            and not writer["padding_or_repetition_used"]
            and writer["first_live_boundary_state_max_abs_residual"] == 0.0
            and writer["first_live_boundary_rgb_max_abs_difference"] == 0
            and writer["first_plan_reference_max_abs_difference"]
            <= writer["reset_numerical_envelope"]
        )
        for writer in writers
    ) and all(
        (
            runner["run_status"] == "complete"
            and runner["plan_updates_consumed"] == requested
            and runner["strict_action_bounds"]
            and runner["evaluation_skipped"]
        )
        for runner in runners
    )
    live_feedback_gate = all(
        len({item["observation_rgb_sha256"] for item in writer["live"]})
        == requested
        for writer in writers
    )

    updates_a = update_steps(runner_a)
    updates_b = update_steps(runner_b)
    comparisons = []
    for record_a, record_b, step_a, step_b in zip(
        writer_a["live"],
        writer_b["live"],
        updates_a,
        updates_b,
        strict=True,
    ):
        plan_a = plan(record_a)
        plan_b = plan(record_b)
        comparisons.append(
            {
                "receiver_timestamp_s": record_a["receiver_timestamp_s"],
                "maximum_plan_delta_m": float(
                    np.max(np.abs(plan_a - plan_b))
                ),
                "endpoint_delta_m": float(
                    np.linalg.norm(plan_a[-1] - plan_b[-1])
                ),
                "acceleration_delta_mps2": abs(
                    float(step_a["action"]["acc"])
                    - float(step_b["action"]["acc"])
                ),
                "steer_rate_delta_radps": abs(
                    float(step_a["action"]["steer_rate"])
                    - float(step_b["action"]["steer_rate"])
                ),
                "mode_a": selected_mode(record_a),
                "mode_b": selected_mode(record_b),
                "acceleration_sign_a": int(
                    np.sign(float(step_a["action"]["acc"]))
                ),
                "acceleration_sign_b": int(
                    np.sign(float(step_b["action"]["acc"]))
                ),
                "rgb_exactly_equal": (
                    record_a["observation_rgb_sha256"]
                    == record_b["observation_rgb_sha256"]
                ),
            }
        )

    exact_reset = all(
        item["maximum_plan_delta_m"] <= writer_a["reset_numerical_envelope"]
        for item in comparisons
    )
    mode_and_action_direction_stable = all(
        item["mode_a"] == item["mode_b"]
        and item["acceleration_sign_a"] == item["acceleration_sign_b"]
        for item in comparisons
    )
    no_adverse_event = all(
        not step["terminated"]
        and not step["truncated"]
        and not step["info_after"]["collision"]
        for runner in runners
        for step in runner["steps"]
    )
    final_state_delta = {
        "ego_box_max_abs_m_or_rad": float(
            np.max(
                np.abs(
                    np.asarray(
                        runner_a["steps"][-1]["info_after"]["ego_box"]
                    )
                    - np.asarray(
                        runner_b["steps"][-1]["info_after"]["ego_box"]
                    )
                )
            )
        ),
        "speed_abs_mps": abs(
            float(runner_a["steps"][-1]["info_after"]["ego_velo"])
            - float(runner_b["steps"][-1]["info_after"]["ego_velo"])
        ),
    }
    return {
        "audit_id": "hugsim_sparsedrive_live_loop_001",
        "scope": "two-second no-actor live feedback capability and sensitivity",
        "plan_count_per_run": requested,
        "comparisons": comparisons,
        "maximum_plan_delta_m": max(
            item["maximum_plan_delta_m"] for item in comparisons
        ),
        "maximum_acceleration_delta_mps2": max(
            item["acceleration_delta_mps2"] for item in comparisons
        ),
        "maximum_steer_rate_delta_radps": max(
            item["steer_rate_delta_radps"] for item in comparisons
        ),
        "final_state_delta": final_state_delta,
        "gates": {
            "live_interface_and_boundary_contract": interface_gate,
            "new_observation_consumed_for_every_plan": live_feedback_gate,
            "same_mode_and_action_direction_across_resets": (
                mode_and_action_direction_stable
            ),
            "no_termination_or_collision": no_adverse_event,
            "exact_plan_reset_reproducibility": exact_reset,
        },
        "evidence_decisions": {
            "live_ad_feedback_capability": {
                "decision": (
                    "accepted"
                    if interface_gate and live_feedback_gate
                    else "rejected"
                ),
                "claim": (
                    "the frozen SparseDrive receiver consumed each new HUGSIM "
                    "six-camera observation and returned a fresh bounded plan"
                ),
            },
            "exact_closed_loop_reset_reproducibility": {
                "decision": "accepted" if exact_reset else "rejected",
                "reason": (
                    "later feedback plans are compared with the frozen "
                    "1e-4 receiver reset numerical envelope"
                ),
            },
            "short_horizon_task_direction_stability": {
                "decision": (
                    "down-weighted"
                    if mode_and_action_direction_stable and no_adverse_event
                    else "rejected"
                ),
                "reason": (
                    "mode, action sign and outcome agree, but no externally "
                    "qualified magnitude tolerance or task acceptance bound exists"
                ),
            },
            "real_world_closed_loop_credibility": {
                "decision": "rejected",
                "reason": "scope exceeds a two-second internal no-actor gate",
            },
        },
    }


def save_visualization(
    analysis: dict[str, Any],
    writer_a: dict[str, Any],
    writer_b: dict[str, Any],
    runner_a: dict[str, Any],
    runner_b: dict[str, Any],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    timestamps = [
        item["receiver_timestamp_s"] for item in analysis["comparisons"]
    ]
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    for label, writer, runner in (
        ("reset A", writer_a, runner_a),
        ("reset B", writer_b, runner_b),
    ):
        updates = update_steps(runner)
        axes[0, 0].plot(
            timestamps,
            [item["plan_geometry"]["final_forward_m"] for item in writer["live"]],
            marker="o",
            label=label,
        )
        axes[0, 1].plot(
            timestamps,
            [item["action"]["acc"] for item in updates],
            marker="o",
            label=label,
        )
        axes[1, 0].plot(
            [0.25 * index for index in range(len(runner["steps"]) + 1)],
            [
                runner["steps"][0]["info_before"]["ego_velo"],
                *[
                    step["info_after"]["ego_velo"]
                    for step in runner["steps"]
                ],
            ],
            marker="o",
            label=label,
        )
    axes[1, 1].semilogy(
        timestamps,
        [
            max(item["maximum_plan_delta_m"], 1e-12)
            for item in analysis["comparisons"]
        ],
        marker="o",
    )
    axes[1, 1].axhline(1e-4, color="red", linestyle="--", label="reset envelope")
    axes[0, 0].set(title="3 s forward plan endpoint", ylabel="forward, m")
    axes[0, 1].set(title="Fresh-plan acceleration", ylabel="m/s²")
    axes[1, 0].set(title="Closed-loop ego speed", xlabel="loop time, s", ylabel="m/s")
    axes[1, 1].set(
        title="Plan divergence across independent resets",
        xlabel="receiver time, s",
        ylabel="max waypoint delta, m",
    )
    for axis in axes.ravel():
        axis.grid(alpha=0.3)
        axis.legend()
    figure.suptitle("SparseDrive ↔ HUGSIM live feedback gate")
    path = output / "live_loop_summary.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    run_dirs = [
        args.run_a.expanduser().resolve(),
        args.run_b.expanduser().resolve(),
    ]
    runners = [load_json(path / "audit_summary.json") for path in run_dirs]
    writers = [
        load_json(path / "sparsedrive_live_summary.json")
        for path in run_dirs
    ]
    analysis = analyze_live_runs(
        runners[0],
        writers[0],
        runners[1],
        writers[1],
    )
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    visual = save_visualization(
        analysis,
        writers[0],
        writers[1],
        runners[0],
        runners[1],
        output,
    )
    analysis["runs"] = [str(path) for path in run_dirs]
    analysis["visualization"] = str(visual)
    report = output / "live_loop_audit.json"
    report.write_text(json.dumps(analysis, indent=2) + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
