#!/usr/bin/env python3
"""Audit complete-future footprint conflict in replicated CF-R closed loops.

The analysis separates two constructs at the common live-loop boundary:

1. stimulus conflict under one shared constant-speed ego continuation;
2. the change in future clearance produced by SparseDrive's own plan.

Only plans whose full six-waypoint actor future is logged are evaluated. No
actor state is repeated, interpolated, extrapolated, or tail-filled.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_hugsim_horizon_factorial import rectangle


CONDITIONS = ("slow", "fast")
HORIZONS_S = np.arange(0.5, 3.0 + 0.25, 0.5, dtype=np.float64)
VALID_PLAN_TIMES_S = (1.5, 2.0, 2.5, 3.0)
EXPECTED_PLAN_TIMES_S = tuple(np.arange(1.5, 5.5 + 0.25, 0.5))
STATE_FIELDS = ("ego_box", "obj_boxes", "ego_velo")
NUMERIC_TOLERANCE = 1e-9
COLORS = {"slow": "#d62728", "fast": "#2ca02c"}
DISPLAY = {
    "slow": "Strong conflict · actor 0.5 m/s",
    "fast": "Weak conflict · actor 1.5 m/s",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def verify_preregistration(
    repo: Path,
    path: Path,
    commit: str,
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(path.relative_to(repo))
    if git_blob(repo, resolved, relative) != path.read_bytes():
        raise ValueError("preregistration differs from its committed version")
    return resolved


def state_difference(first: dict[str, Any], second: dict[str, Any]) -> float:
    differences = []
    for field in STATE_FIELDS:
        differences.append(
            float(
                np.max(
                    np.abs(
                        np.asarray(first[field], dtype=np.float64)
                        - np.asarray(second[field], dtype=np.float64)
                    )
                )
            )
        )
    return max(differences)


def state_timeline(audit: dict[str, Any]) -> dict[float, dict[str, Any]]:
    steps = audit["steps"]
    if not steps:
        raise ValueError("closed-loop audit contains no steps")
    states = [steps[0]["info_before"]]
    for index, step in enumerate(steps):
        if index and state_difference(states[-1], step["info_before"]) > NUMERIC_TOLERANCE:
            raise ValueError(f"state discontinuity before environment step {index}")
        states.append(step["info_after"])
    result: dict[float, dict[str, Any]] = {}
    for state in states:
        timestamp = round(float(state["timestamp"]), 9)
        if timestamp in result:
            raise ValueError(f"duplicate state timestamp: {timestamp}")
        if len(state["obj_boxes"]) != 1:
            raise ValueError("future-conflict audit requires exactly one actor")
        result[timestamp] = state
    expected = np.arange(1.5, 6.0 + 0.125, 0.25)
    if not np.allclose(sorted(result), expected, atol=NUMERIC_TOLERANCE):
        raise ValueError("environment state timeline is incomplete or misaligned")
    return result


def plan_records(writer: dict[str, Any]) -> dict[float, dict[str, Any]]:
    if writer["status"] != "complete" or writer["padding_or_repetition_used"]:
        raise ValueError("receiver run is incomplete or used plan padding")
    records = {}
    for record in writer["live"]:
        timestamp = round(float(record["environment_timestamp_s"]), 9)
        plan = np.asarray(
            record["native"]["final_planning_values"],
            dtype=np.float64,
        )
        if plan.shape != (6, 2) or not np.isfinite(plan).all():
            raise ValueError(f"invalid six-waypoint plan at {timestamp}")
        if timestamp in records:
            raise ValueError(f"duplicate receiver plan timestamp: {timestamp}")
        records[timestamp] = record
    if not np.allclose(
        sorted(records),
        EXPECTED_PLAN_TIMES_S,
        atol=NUMERIC_TOLERANCE,
    ):
        raise ValueError("receiver plan timestamps are incomplete or misaligned")
    return records


def world_boxes_from_plan(
    plan_right_forward: np.ndarray,
    origin_box: list[float],
) -> list[list[float]]:
    plan = np.asarray(plan_right_forward, dtype=np.float64)
    origin = np.asarray(origin_box, dtype=np.float64)
    if plan.shape != (6, 2):
        raise ValueError(f"expected plan shape (6, 2), got {plan.shape}")
    yaw = float(origin[6])
    forward = np.asarray([np.cos(yaw), np.sin(yaw)], dtype=np.float64)
    right = np.asarray([np.sin(yaw), -np.cos(yaw)], dtype=np.float64)
    centres = (
        origin[None, :2]
        + plan[:, 1:2] * forward[None, :]
        + plan[:, 0:1] * right[None, :]
    )
    previous = origin[:2]
    previous_yaw = yaw
    boxes = []
    for centre in centres:
        delta = centre - previous
        if float(np.linalg.norm(delta)) > NUMERIC_TOLERANCE:
            previous_yaw = float(np.arctan2(delta[1], delta[0]))
        boxes.append(
            [
                float(centre[0]),
                float(centre[1]),
                float(origin[2]),
                float(origin[3]),
                float(origin[4]),
                float(origin[5]),
                previous_yaw,
            ]
        )
        previous = centre
    return boxes


def constant_speed_plan(speed_mps: float) -> np.ndarray:
    if speed_mps < 0 or not np.isfinite(speed_mps):
        raise ValueError("constant-speed reference requires finite nonnegative speed")
    return np.stack(
        [np.zeros_like(HORIZONS_S), HORIZONS_S * speed_mps],
        axis=1,
    )


def conflict_metrics(
    plan: np.ndarray,
    plan_time_s: float,
    states: dict[float, dict[str, Any]],
) -> dict[str, Any]:
    origin = states[round(plan_time_s, 9)]
    future_ego_boxes = world_boxes_from_plan(plan, origin["ego_box"])
    actor_boxes = []
    clearances = []
    for horizon, ego_box in zip(HORIZONS_S, future_ego_boxes, strict=True):
        target_time = round(plan_time_s + float(horizon), 9)
        if target_time not in states:
            raise ValueError(
                f"missing exact actor future at t={target_time:.2f} s"
            )
        actor_box = states[target_time]["obj_boxes"][0]
        actor_boxes.append(actor_box)
        clearances.append(float(rectangle(ego_box).distance(rectangle(actor_box))))
    minimum = min(clearances)
    closest_index = clearances.index(minimum)
    return {
        "plan_time_s": float(plan_time_s),
        "horizons_s": HORIZONS_S.astype(float).tolist(),
        "clearance_m": clearances,
        "minimum_clearance_m": float(minimum),
        "earliest_time_of_minimum_clearance_s": float(
            HORIZONS_S[closest_index]
        ),
        "zero_clearance_path_conflict": bool(minimum <= NUMERIC_TOLERANCE),
        "future_ego_boxes": future_ego_boxes,
        "future_actor_boxes": actor_boxes,
    }


def selected_mode(record: dict[str, Any]) -> int:
    command = int(
        np.argmax(
            np.asarray(
                record["input_contract"][
                    "command_one_hot_right_left_straight"
                ],
                dtype=np.float64,
            )
        )
    )
    scores = np.asarray(
        record["native"]["planning_score_values"],
        dtype=np.float64,
    )
    if scores.shape != (3, 6) or not np.isfinite(scores).all():
        raise ValueError("invalid native planning-score matrix")
    return int(np.argmax(scores[command]))


def expected_order_decision(
    lower_values: list[float],
    higher_values: list[float],
) -> dict[str, Any]:
    if len(lower_values) != 2 or len(higher_values) != 2:
        raise ValueError("replicated decision requires two values per condition")
    paired_effects = [
        higher - lower
        for lower, higher in zip(lower_values, higher_values, strict=True)
    ]
    repeat = max(float(np.ptp(lower_values)), float(np.ptp(higher_values)))
    direction = all(value > NUMERIC_TOLERANCE for value in paired_effects)
    robust = direction and min(paired_effects) > repeat + NUMERIC_TOLERANCE
    return {
        "lower_values": lower_values,
        "higher_values": higher_values,
        "paired_effects_higher_minus_lower": paired_effects,
        "minimum_condition_effect": min(paired_effects),
        "maximum_same_condition_repeat_range": repeat,
        "strict_direction_passed": direction,
        "effect_exceeds_repeat_range": robust,
        "decision": (
            "accepted"
            if robust
            else "down-weighted"
            if direction
            else "rejected"
        ),
    }


def validate_input(
    repo: Path,
    spec: dict[str, Any],
    condition: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = repo / spec["run"]
    audit_path = run / "audit_summary.json"
    writer_path = run / "sparsedrive_live_summary.json"
    if sha256_file(audit_path) != spec["audit_summary_sha256"]:
        raise ValueError(f"audit input hash changed: {run}")
    if sha256_file(writer_path) != spec["sparsedrive_live_summary_sha256"]:
        raise ValueError(f"receiver input hash changed: {run}")
    audit = load_json(audit_path)
    writer = load_json(writer_path)
    expected_speed = 0.5 if condition == "slow" else 1.5
    actor_speed = float(
        audit["source_assets"]["vehicle_assets"][0]["initial_state"][
            "velocity_mps"
        ]
    )
    if audit["run_status"] != "complete" or not np.isclose(
        actor_speed,
        expected_speed,
        atol=NUMERIC_TOLERANCE,
    ):
        raise ValueError(f"run identity differs: {run}")
    return audit, writer


def analyze(
    repo: Path,
    preregistration: dict[str, Any],
) -> dict[str, Any]:
    runs: dict[str, list[dict[str, Any]]] = {key: [] for key in CONDITIONS}
    boundary_boxes = []
    reference_plans = []
    for condition in CONDITIONS:
        for reset, spec in enumerate(
            preregistration["inputs"][condition],
            start=1,
        ):
            audit, writer = validate_input(repo, spec, condition)
            states = state_timeline(audit)
            plans = plan_records(writer)
            diagnostics = {}
            for timestamp in VALID_PLAN_TIMES_S:
                plan = np.asarray(
                    plans[timestamp]["native"]["final_planning_values"],
                    dtype=np.float64,
                )
                diagnostics[str(timestamp)] = conflict_metrics(
                    plan,
                    timestamp,
                    states,
                )
            boundary = states[1.5]
            reference = constant_speed_plan(float(boundary["ego_velo"]))
            reference_metrics = conflict_metrics(reference, 1.5, states)
            own_metrics = diagnostics["1.5"]
            mode = selected_mode(plans[1.5])
            boundary_boxes.append(np.asarray(boundary["ego_box"], dtype=np.float64))
            reference_plans.append(reference)
            runs[condition].append(
                {
                    "condition": condition,
                    "reset": reset,
                    "input": spec,
                    "selected_mode_at_1_5_s": mode,
                    "handoff_ego_speed_mps": float(boundary["ego_velo"]),
                    "common_reference": reference_metrics,
                    "sparsedrive_plan": own_metrics,
                    "mitigation_gain_m": float(
                        own_metrics["minimum_clearance_m"]
                        - reference_metrics["minimum_clearance_m"]
                    ),
                    "complete_horizon_diagnostics": diagnostics,
                }
            )

    boundary_residual = max(
        float(np.max(np.abs(value - boundary_boxes[0])))
        for value in boundary_boxes[1:]
    )
    reference_residual = max(
        float(np.max(np.abs(value - reference_plans[0])))
        for value in reference_plans[1:]
    )
    if max(boundary_residual, reference_residual) > NUMERIC_TOLERANCE:
        raise ValueError("handoff ego state or reference path is not common")

    slow_probe = [
        item["common_reference"]["minimum_clearance_m"]
        for item in runs["slow"]
    ]
    fast_probe = [
        item["common_reference"]["minimum_clearance_m"]
        for item in runs["fast"]
    ]
    stimulus = expected_order_decision(slow_probe, fast_probe)
    stimulus["expected"] = "slow reference clearance < fast reference clearance"

    slow_gain = [item["mitigation_gain_m"] for item in runs["slow"]]
    fast_gain = [item["mitigation_gain_m"] for item in runs["fast"]]
    mitigation_order = expected_order_decision(fast_gain, slow_gain)
    modes = [
        item["selected_mode_at_1_5_s"]
        for condition in CONDITIONS
        for item in runs[condition]
    ]
    same_mode = len(set(modes)) == 1
    all_positive = all(
        value > NUMERIC_TOLERANCE for value in slow_gain + fast_gain
    )
    any_negative = any(
        value < -NUMERIC_TOLERANCE for value in slow_gain + fast_gain
    )
    if (
        same_mode
        and all_positive
        and mitigation_order["decision"] == "accepted"
    ):
        mitigation_decision = "accepted"
    elif any_negative:
        mitigation_decision = "rejected"
    else:
        mitigation_decision = "down-weighted"
    mitigation = {
        "expected": (
            "all gains > 0 and slow mitigation gain > fast mitigation gain"
        ),
        "same_selected_mode": same_mode,
        "selected_modes_slow_then_fast": modes,
        "slow_gain_m": slow_gain,
        "fast_gain_m": fast_gain,
        "all_gains_strictly_positive": all_positive,
        "any_plan_reduces_clearance": any_negative,
        "condition_order": mitigation_order,
        "decision": mitigation_decision,
    }

    if stimulus["decision"] == "accepted" and mitigation_decision == "accepted":
        overall = "accepted"
    elif (
        stimulus["decision"] != "rejected"
        and mitigation_decision != "rejected"
    ):
        overall = "down-weighted"
    else:
        overall = "rejected"

    return {
        "audit_id": "hugsim_cf_r_future_conflict_001",
        "scope": (
            "complete-future simulator-internal footprint conflict and "
            "target-AD mitigation at the shared CF-R handoff"
        ),
        "validity_gate": {
            "decision": "accepted",
            "included_plan_timestamps_s": list(VALID_PLAN_TIMES_S),
            "excluded_incomplete_plan_timestamps_s": [3.5, 4.0, 4.5, 5.0, 5.5],
            "included_plan_count_per_run": len(VALID_PLAN_TIMES_S),
            "total_plan_count_per_run": len(EXPECTED_PLAN_TIMES_S),
            "exact_future_states_per_included_plan": len(HORIZONS_S),
            "tail_fill_used": False,
            "maximum_handoff_ego_box_residual": boundary_residual,
            "maximum_common_reference_plan_residual": reference_residual,
        },
        "common_path_stimulus_conflict": stimulus,
        "target_ad_mitigation": mitigation,
        "runs": runs,
        "overall_internal_indicator_decision": overall,
        "real_world_risk_or_response_credibility": {
            "decision": "rejected",
            "reason": (
                "state boxes and response magnitude lack independent real-world "
                "qualification; this is a simulator-internal instrument audit"
            ),
        },
    }


def write_csv(path: Path, analysis: dict[str, Any]) -> None:
    fields = [
        "condition",
        "reset",
        "plan_time_s",
        "selected_mode_at_1_5_s",
        "reference_min_clearance_m",
        "own_plan_min_clearance_m",
        "mitigation_gain_m",
        "own_plan_tca_s",
        "own_plan_zero_clearance",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for condition in CONDITIONS:
            for run in analysis["runs"][condition]:
                for timestamp in VALID_PLAN_TIMES_S:
                    diagnostic = run["complete_horizon_diagnostics"][str(timestamp)]
                    boundary = timestamp == 1.5
                    writer.writerow(
                        {
                            "condition": condition,
                            "reset": run["reset"],
                            "plan_time_s": timestamp,
                            "selected_mode_at_1_5_s": (
                                run["selected_mode_at_1_5_s"] if boundary else ""
                            ),
                            "reference_min_clearance_m": (
                                run["common_reference"]["minimum_clearance_m"]
                                if boundary
                                else ""
                            ),
                            "own_plan_min_clearance_m": diagnostic[
                                "minimum_clearance_m"
                            ],
                            "mitigation_gain_m": (
                                run["mitigation_gain_m"] if boundary else ""
                            ),
                            "own_plan_tca_s": diagnostic[
                                "earliest_time_of_minimum_clearance_s"
                            ],
                            "own_plan_zero_clearance": diagnostic[
                                "zero_clearance_path_conflict"
                            ],
                        }
                    )


def make_plot(path: Path, analysis: dict[str, Any]) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    for condition in CONDITIONS:
        for run in analysis["runs"][condition]:
            suffix = f"r{run['reset']}"
            axes[0, 0].plot(
                HORIZONS_S,
                run["common_reference"]["clearance_m"],
                marker="o",
                color=COLORS[condition],
                alpha=0.65,
                label=f"{DISPLAY[condition]} · {suffix}",
            )
            axes[0, 1].plot(
                HORIZONS_S,
                run["sparsedrive_plan"]["clearance_m"],
                marker="o",
                color=COLORS[condition],
                alpha=0.65,
                label=f"{DISPLAY[condition]} · {suffix}",
            )
    axes[0, 0].set(
        title="Shared constant-speed path at t=1.5 s",
        xlabel="Future horizon (s)",
        ylabel="Footprint clearance (m)",
    )
    axes[0, 1].set(
        title="SparseDrive own plan at t=1.5 s",
        xlabel="Future horizon (s)",
        ylabel="Footprint clearance (m)",
    )
    for axis in axes[0]:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)

    labels = []
    probe = []
    own = []
    gains = []
    colors = []
    for condition in CONDITIONS:
        for run in analysis["runs"][condition]:
            labels.append(f"{condition}\nr{run['reset']}")
            probe.append(run["common_reference"]["minimum_clearance_m"])
            own.append(run["sparsedrive_plan"]["minimum_clearance_m"])
            gains.append(run["mitigation_gain_m"])
            colors.append(COLORS[condition])
    positions = np.arange(len(labels))
    axes[1, 0].bar(
        positions - 0.18,
        probe,
        width=0.36,
        color="#9e9e9e",
        label="shared path",
    )
    axes[1, 0].bar(
        positions + 0.18,
        own,
        width=0.36,
        color=colors,
        label="SparseDrive plan",
    )
    axes[1, 0].set(
        title="Minimum 3 s clearance at shared handoff",
        ylabel="Minimum footprint clearance (m)",
        xticks=positions,
        xticklabels=labels,
    )
    axes[1, 0].grid(axis="y", alpha=0.25)
    axes[1, 0].legend(fontsize=8)

    for condition in CONDITIONS:
        for run in analysis["runs"][condition]:
            values = [
                run["complete_horizon_diagnostics"][str(timestamp)][
                    "minimum_clearance_m"
                ]
                for timestamp in VALID_PLAN_TIMES_S
            ]
            axes[1, 1].plot(
                VALID_PLAN_TIMES_S,
                values,
                marker="o",
                color=COLORS[condition],
                alpha=0.65,
                label=f"{DISPLAY[condition]} · r{run['reset']}",
            )
    axes[1, 1].set(
        title="Own-plan diagnostic where full actor future exists",
        xlabel="Plan timestamp (s)",
        ylabel="Minimum future clearance (m)",
        xticks=VALID_PLAN_TIMES_S,
    )
    axes[1, 1].grid(alpha=0.25)
    axes[1, 1].legend(fontsize=8)
    figure.suptitle(
        "CF-R complete-future conflict audit · "
        f"{analysis['overall_internal_indicator_decision']}",
        fontsize=16,
    )
    figure.savefig(path, dpi=170)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    preregistration_commit = verify_preregistration(
        repo,
        preregistration_path,
        args.preregistration_commit,
    )
    preregistration = load_json(preregistration_path)
    analysis = analyze(repo, preregistration)
    analysis["preregistration"] = {
        "path": str(preregistration_path),
        "commit": preregistration_commit,
        "sha256": sha256_file(preregistration_path),
    }
    analysis["analysis_script"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": sha256_file(Path(__file__).resolve()),
    }
    output.mkdir(parents=True)
    json_path = output / "cf_r_future_conflict_audit.json"
    csv_path = output / "cf_r_future_conflict_rows.csv"
    plot_path = output / "cf_r_future_conflict_summary.png"
    analysis["artifacts"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "plot": str(plot_path),
    }
    with json_path.open("w", encoding="utf-8") as stream:
        json.dump(analysis, stream, indent=2)
    write_csv(csv_path, analysis)
    make_plot(plot_path, analysis)
    print(json.dumps(
        {
            "overall": analysis["overall_internal_indicator_decision"],
            "validity_gate": analysis["validity_gate"]["decision"],
            "stimulus": analysis["common_path_stimulus_conflict"]["decision"],
            "mitigation": analysis["target_ad_mitigation"]["decision"],
            "output": str(output),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
