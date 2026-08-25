#!/usr/bin/env python3
"""Analyze the preregistered HUGSIM–SparseDrive actuation-contract audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


CONDITIONS = ("below", "near", "above")
COLORS = {"below": "#d62728", "near": "#ff7f0e", "above": "#2ca02c"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
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
    preregistration: dict[str, Any],
    commit: str,
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(path.resolve().relative_to(repo))
    if git_blob(repo, resolved, relative) != path.read_bytes():
        raise ValueError("preregistration differs from committed bytes")
    script_relative = "scripts/analyze_hugsim_sparsedrive_actuation_contract.py"
    observed = hashlib.sha256(git_blob(repo, resolved, script_relative)).hexdigest()
    if observed != preregistration["implementation"]["analysis_script_sha256"]:
        raise ValueError("analysis script differs from preregistered hash")
    return resolved


def longitudinal_progress(boundary_box: list[float], box: list[float]) -> float:
    boundary = np.asarray(boundary_box, dtype=np.float64)
    current = np.asarray(box, dtype=np.float64)
    heading = float(boundary[6])
    forward = np.asarray([np.cos(heading), np.sin(heading)])
    return float(np.dot(current[:2] - boundary[:2], forward))


def planning_modes(writer: dict[str, Any]) -> list[dict[str, int]]:
    modes = []
    for row in writer["live"]:
        scores = np.asarray(row["native"]["planning_score_values"], dtype=float)
        command_mode, trajectory_mode = np.unravel_index(
            int(np.argmax(scores)), scores.shape
        )
        modes.append(
            {
                "plan_index": int(row["plan_index"]),
                "command_mode": int(command_mode),
                "trajectory_mode": int(trajectory_mode),
            }
        )
    return modes


def validate_strict_regression(
    repo: Path,
    preregistration: dict[str, Any],
) -> dict[str, Any]:
    spec = preregistration["strict_regression"]
    path = repo / spec["output"]
    audit = load_json(path / "audit_summary.json")
    failure = audit["actuation_contract"]["failure"]
    passed = bool(
        audit["run_status"] == "rejected_actuation_contract"
        and audit["actuation_contract"]["mode"] == "strict_audit"
        and failure is not None
        and failure["decision"] == "rejected_out_of_bounds"
        and failure["applied_control"] is None
        and failure["saturation_active"]
        and audit["completed_steps"] == failure["attempted_step_id"]
        and len(audit["steps"]) == audit["completed_steps"]
    )
    return {
        "decision": "accepted" if passed else "rejected",
        "output": str(path),
        "completed_environment_steps": int(audit["completed_steps"]),
        "rejected_attempted_step_id": failure["attempted_step_id"] if failure else None,
        "raw_control": failure["raw_control"] if failure else None,
        "bounds": failure["bounds"] if failure else None,
        "applied_control": failure["applied_control"] if failure else None,
        "reason": (
            "out-of-bounds raw command was retained and env.step was not called"
            if passed
            else "strict fail-closed regression did not satisfy its frozen gate"
        ),
    }


def validate_bounded_run(
    repo: Path,
    preregistration: dict[str, Any],
    condition: str,
    reset: int,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    spec = preregistration["bounded_runs"][condition][reset - 1]
    path = repo / spec["output"]
    audit = load_json(path / "audit_summary.json")
    writer = load_json(path / "sparsedrive_live_summary.json")
    failures: list[str] = []
    if audit["run_status"] != "complete":
        failures.append("runner incomplete")
    if audit["requested_steps"] != preregistration["live_loop"]["environment_steps"]:
        failures.append("environment-step count differs")
    if audit["control_hold_steps"] != preregistration["live_loop"]["control_hold_steps"]:
        failures.append("control-hold differs")
    contract = audit["actuation_contract"]
    if contract["mode"] != "bounded_projection":
        failures.append("wrong actuation contract")
    if len(contract["attempts"]) != audit["requested_steps"]:
        failures.append("contract record missing for one or more steps")
    for attempt in contract["attempts"]:
        applied = attempt["applied_control"]
        if applied is None:
            failures.append("bounded command was rejected")
            continue
        for name, value in applied.items():
            limits = attempt["bounds"][name]
            if not limits["low"] <= value <= limits["high"]:
                failures.append(f"applied {name} outside qualified bounds")
    if audit["source_assets"]["scenario_yaml_sha256"] != spec["config_sha256"]:
        failures.append("scenario hash differs")
    warm = audit["warm_start"]
    if (
        not warm["enabled"]
        or warm["step_count"] != preregistration["warm_start"]["environment_steps"]
        or warm["maximum_state_residual"] > preregistration["warm_start"]["state_atol"]
        or warm["maximum_rgb_difference"] != 0
    ):
        failures.append("warm-start replay gate failed")
    for name, expected_hash in spec["source_input_sha256"].items():
        if warm["source_input_sha256"].get(name) != expected_hash:
            failures.append(f"warm-start source hash differs: {name}")
    if writer["status"] != "complete":
        failures.append("receiver incomplete")
    if writer["plans_sent"] != preregistration["live_loop"]["plan_updates"]:
        failures.append("receiver plan count differs")
    if writer["padding_or_repetition_used"]:
        failures.append("receiver plan padding or repetition used")
    if writer["first_live_boundary_state_max_abs_residual"] != 0.0:
        failures.append("first live state differs from source boundary")
    if writer["first_live_boundary_rgb_max_abs_difference"] != 0:
        failures.append("first live RGB differs from source boundary")
    if (
        writer["first_plan_reference_max_abs_difference"]
        > writer["reset_numerical_envelope"]
    ):
        failures.append("first plan differs from frozen reset reference")
    if sha256(Path(writer["first_plan_reference_native"])) != spec["reference_native_sha256"]:
        failures.append("reference native hash differs")
    return audit, writer, failures


def summarize_run(
    audit: dict[str, Any],
    writer: dict[str, Any],
    path: Path,
    condition: str,
    reset: int,
) -> dict[str, Any]:
    first = audit["steps"][0]["info_before"]
    final = audit["steps"][-1]["info_after"]
    attempts = audit["actuation_contract"]["attempts"]
    saturated = [item for item in attempts if item["saturation_active"]]
    max_violation = {
        name: max(float(item["violation_amount"][name]) for item in attempts)
        for name in ("acc", "steer_rate")
    }
    artifact_paths = {
        "audit_summary": path / "audit_summary.json",
        "receiver_summary": path / "sparsedrive_live_summary.json",
        "receiver_native_output": path / "sparsedrive_live_native_outputs.pt",
        "video": path / "video.mp4",
        "runner_log": path.with_name(path.name + ".runner.log"),
        "writer_log": path.with_name(path.name + ".writer.log"),
    }
    return {
        "reset_identity": {
            "condition": condition,
            "independent_process_reset": reset,
            "audit_repo_commit": audit["audit_repo"]["commit"],
        },
        "output": str(path),
        "world_time": {
            "start_s": float(first["timestamp"]),
            "end_s": float(final["timestamp"]),
            "elapsed_s": float(final["timestamp"] - first["timestamp"]),
        },
        "final_ego_progress_m": longitudinal_progress(
            first["ego_box"], final["ego_box"]
        ),
        "final_ego_speed_mps": float(final["ego_velo"]),
        "collision_observed": any(bool(step["info_after"]["collision"]) for step in audit["steps"]),
        "saturation_step_count": len(saturated),
        "saturation_fraction": len(saturated) / len(attempts),
        "first_saturation_elapsed_s": (
            float(saturated[0]["timestamp_before_s"] - first["timestamp"])
            if saturated
            else None
        ),
        "maximum_violation_amount": max_violation,
        "maximum_projection_residual_l2": max(
            float(item["projection_residual_l2"]) for item in attempts
        ),
        "cumulative_projection_residual_l2": sum(
            float(item["projection_residual_l2"]) for item in attempts
        ),
        "planning_mode_sequence": planning_modes(writer),
        "fallback_or_plan_repetition": bool(writer["padding_or_repetition_used"]),
        "run_status": audit["run_status"],
        "receiver_status": writer["status"],
        "terminated": bool(audit["terminated"]),
        "truncated": bool(audit["truncated"]),
        "output_sha256": {
            name: sha256(artifact_path)
            for name, artifact_path in artifact_paths.items()
        },
    }


def order_decision(runs: dict[str, list[dict[str, Any]]], field: str) -> dict[str, Any]:
    values = {
        condition: [float(row[field]) for row in runs[condition]]
        for condition in CONDITIONS
    }
    paired_margins = []
    for reset in range(2):
        paired_margins.append(
            {
                "reset": reset + 1,
                "near_minus_below": values["near"][reset] - values["below"][reset],
                "above_minus_near": values["above"][reset] - values["near"][reset],
            }
        )
    direction = all(
        item["near_minus_below"] >= 0.0 and item["above_minus_near"] >= 0.0
        for item in paired_margins
    )
    repeat_range = max(float(np.ptp(values[condition])) for condition in CONDITIONS)
    minimum_effect = min(
        min(item["near_minus_below"], item["above_minus_near"])
        for item in paired_margins
    )
    exceeds_repeat = direction and minimum_effect > repeat_range
    return {
        "expected": "below <= near <= above",
        "values": values,
        "paired_adjacent_margins": paired_margins,
        "maximum_within_condition_repeat_range": repeat_range,
        "minimum_adjacent_condition_effect": minimum_effect,
        "direction_passed": direction,
        "effect_exceeds_repeat_range": exceeds_repeat,
        "decision": "accepted" if exceeds_repeat else ("down-weighted" if direction else "rejected"),
    }


def analyze(
    preregistration: dict[str, Any],
    repo: Path,
    preregistration_commit: str,
) -> dict[str, Any]:
    strict = validate_strict_regression(repo, preregistration)
    runs: dict[str, list[dict[str, Any]]] = {condition: [] for condition in CONDITIONS}
    failures: dict[str, list[str]] = {}
    mechanics_rows = []
    for condition in CONDITIONS:
        for reset in (1, 2):
            audit, writer, run_failures = validate_bounded_run(
                repo, preregistration, condition, reset
            )
            key = f"{condition}-reset{reset}"
            failures[key] = run_failures
            path = repo / preregistration["bounded_runs"][condition][reset - 1]["output"]
            row = summarize_run(audit, writer, path, condition, reset)
            runs[condition].append(row)
            mechanics_rows.append(
                {
                    "run": key,
                    "raw_and_applied_recorded_each_step": len(
                        audit["actuation_contract"]["attempts"]
                    )
                    == audit["requested_steps"],
                    "all_applied_actions_in_bounds": not any(
                        "outside qualified bounds" in failure for failure in run_failures
                    ),
                    "saturation_step_count": row["saturation_step_count"],
                    "maximum_violation_amount": row["maximum_violation_amount"],
                }
            )
    all_complete = all(not item for item in failures.values())
    progress = order_decision(runs, "final_ego_progress_m")
    speed = order_decision(runs, "final_ego_speed_mps")
    internal_direction = (
        "accepted"
        if all_complete
        and progress["decision"] == "accepted"
        and speed["decision"] == "accepted"
        else (
            "down-weighted"
            if all_complete
            and progress["direction_passed"]
            and speed["direction_passed"]
            else "rejected"
        )
    )
    return {
        "audit_id": preregistration["audit_id"],
        "preregistration_commit": preregistration_commit,
        "contract_mechanics": {
            "strict_fail_closed": strict,
            "bounded_projection": {
                "decision": "accepted" if all_complete else "rejected",
                "run_failures": failures,
                "rows": mechanics_rows,
            },
        },
        "bounded_runs": runs,
        "projection_burden": {
            "role": "diagnostic only; no post-hoc acceptance threshold",
            "per_run": {
                f"{condition}-reset{index + 1}": {
                    key: row[key]
                    for key in (
                        "saturation_step_count",
                        "saturation_fraction",
                        "first_saturation_elapsed_s",
                        "maximum_violation_amount",
                        "maximum_projection_residual_l2",
                        "cumulative_projection_residual_l2",
                    )
                }
                for condition in CONDITIONS
                for index, row in enumerate(runs[condition])
            },
        },
        "direct_outcomes": {
            "final_ego_progress": progress,
            "final_ego_speed": speed,
            "planning_modes": {
                condition: [row["planning_mode_sequence"] for row in runs[condition]]
                for condition in CONDITIONS
            },
            "fallback_or_plan_repetition_detected": any(
                row["fallback_or_plan_repetition"]
                for condition in CONDITIONS
                for row in runs[condition]
            ),
        },
        "evidence_decisions": {
            "strict_contract_regression": strict["decision"],
            "bounded_contract_execution": "accepted" if all_complete else "rejected",
            "bounded_internal_direction_and_repeat": internal_direction,
            "near_stop_clearance_or_physical_collision": "rejected",
            "real_world_closed_loop_credibility": "rejected",
        },
        "strongest_allowed_claim": preregistration["strongest_allowed_claim"],
        "limitations": preregistration["forbidden_claims"],
    }


def save_plot(analysis: dict[str, Any], output: Path) -> Path:
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    x = np.arange(len(CONDITIONS))
    for axis, field, title, unit in (
        (axes[0, 0], "final_ego_progress_m", "Final longitudinal progress", "m"),
        (axes[0, 1], "final_ego_speed_mps", "Final ego speed", "m/s"),
    ):
        for reset in (0, 1):
            values = [
                analysis["bounded_runs"][condition][reset][field]
                for condition in CONDITIONS
            ]
            axis.plot(x, values, marker="o", label=f"independent reset {reset + 1}")
        axis.set_xticks(x, CONDITIONS)
        axis.set(title=title, ylabel=unit)
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)

    width = 0.35
    for reset in (0, 1):
        values = [
            analysis["bounded_runs"][condition][reset]["saturation_fraction"]
            for condition in CONDITIONS
        ]
        axes[1, 0].bar(x + (reset - 0.5) * width, values, width=width, label=f"reset {reset + 1}")
    axes[1, 0].set_xticks(x, CONDITIONS)
    axes[1, 0].set(title="Projection burden", ylabel="saturated step fraction")
    axes[1, 0].grid(axis="y", alpha=0.3)
    axes[1, 0].legend(fontsize=8)

    for condition in CONDITIONS:
        for reset, row in enumerate(analysis["bounded_runs"][condition], start=1):
            modes = [item["trajectory_mode"] for item in row["planning_mode_sequence"]]
            axes[1, 1].plot(
                range(len(modes)), modes, color=COLORS[condition], alpha=0.55,
                marker="o", label=f"{condition} r{reset}"
            )
    axes[1, 1].set(
        title="Selected native planning-mode sequence",
        xlabel="live plan index",
        ylabel="trajectory-mode index",
    )
    axes[1, 1].grid(alpha=0.3)
    axes[1, 1].legend(fontsize=7, ncol=2)
    figure.suptitle("HUGSIM–SparseDrive actuation contract qualification 001")
    path = output / "actuation_contract_summary.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def save_report(analysis: dict[str, Any], output: Path) -> Path:
    progress = analysis["direct_outcomes"]["final_ego_progress"]
    speed = analysis["direct_outcomes"]["final_ego_speed"]
    lines = [
        "# HUGSIM–SparseDrive actuation contract qualification 001",
        "",
        "## Decisions",
        "",
    ]
    for name, decision in analysis["evidence_decisions"].items():
        lines.append(f"- `{name}`: `{decision}`")
    lines.extend(
        [
            "",
            "## Direct bounded-loop outcomes",
            "",
            f"- Final progress order: `{progress['decision']}`; direction={progress['direction_passed']}; effect exceeds repeat={progress['effect_exceeds_repeat_range']}.",
            f"- Final speed order: `{speed['decision']}`; direction={speed['direction_passed']}; effect exceeds repeat={speed['effect_exceeds_repeat_range']}.",
            "- Projection burden is diagnostic and has no post-hoc pass threshold.",
            "- Near-stop clearance, physical collision, and real-world closed-loop credibility remain rejected/unqualified.",
            "",
            "## Per-run values",
            "",
            "| condition | reset | progress (m) | final speed (m/s) | saturated steps | fraction | cumulative residual L2 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for condition in CONDITIONS:
        for reset, row in enumerate(analysis["bounded_runs"][condition], start=1):
            lines.append(
                f"| {condition} | {reset} | {row['final_ego_progress_m']:.6f} | "
                f"{row['final_ego_speed_mps']:.6f} | {row['saturation_step_count']} | "
                f"{row['saturation_fraction']:.3f} | "
                f"{row['cumulative_projection_residual_l2']:.6f} |"
            )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            analysis["strongest_allowed_claim"],
            "",
        ]
    )
    path = output / "actuation_contract_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.resolve()
    preregistration = load_json(preregistration_path)
    commit = verify_preregistration(
        repo, preregistration_path, preregistration, args.preregistration_commit
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    analysis = analyze(preregistration, repo, commit)
    analysis["analysis_implementation"] = {
        "preregistered_script_sha256": preregistration["implementation"][
            "analysis_script_sha256"
        ],
        "executed_script_sha256": sha256(Path(__file__).resolve()),
        "erratum": (
            "the executed script corrects the preregistration hash field lookup "
            "and completes preregistered provenance and projection-burden "
            "reporting fields; measurements and decision rules are unchanged"
        ),
    }
    audit_path = output / "actuation_contract_audit.json"
    audit_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    save_plot(analysis, output)
    save_report(analysis, output)
    print(audit_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
