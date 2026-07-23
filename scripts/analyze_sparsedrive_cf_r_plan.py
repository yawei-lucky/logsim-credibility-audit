#!/usr/bin/env python3
"""Audit whether the frozen CF-R conflict order reaches SparseDrive planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


CONDITIONS = ("slow", "nominal", "fast")
PAIRS = (("slow", "nominal"), ("nominal", "fast"), ("slow", "fast"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--receiver-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def verify_preregistration(
    repo: Path,
    commit: str,
    preregistration_path: Path,
    preregistration: dict[str, Any],
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(preregistration_path.relative_to(repo))
    if git_blob(repo, resolved, relative) != preregistration_path.read_bytes():
        raise ValueError("preregistration differs from committed version")
    script_relative = str(Path(__file__).resolve().relative_to(repo))
    committed_script = git_blob(repo, resolved, script_relative)
    if hashlib.sha256(committed_script).hexdigest() != preregistration[
        "analysis_script_sha256"
    ]:
        raise ValueError("analysis script hash differs from preregistration")
    return resolved


def verify_inputs(
    repo: Path,
    preregistration: dict[str, Any],
    receiver: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    frozen_source = preregistration["receiver"]["source"]
    if receiver["source"]["commit"] != frozen_source["commit"]:
        raise ValueError("SparseDrive source commit differs from preregistration")
    if receiver["source"]["working_diff_sha256"] != frozen_source[
        "working_diff_sha256"
    ]:
        raise ValueError("SparseDrive compatibility diff differs from preregistration")
    if receiver["adapter"]["runner_sha256"] != preregistration["receiver"][
        "runner_sha256"
    ]:
        raise ValueError("receiver runner differs from preregistration")
    if receiver["adapter"]["compatibility_patch_sha256"] != preregistration[
        "receiver"
    ]["compatibility_patch_sha256"]:
        raise ValueError("receiver compatibility patch differs from preregistration")
    if receiver["model"]["checkpoint_sha256"] != preregistration["receiver"][
        "checkpoint_sha256"
    ]:
        raise ValueError("SparseDrive checkpoint differs from preregistration")
    if receiver["model"]["config_sha256"] != preregistration["receiver"][
        "config_sha256"
    ]:
        raise ValueError("SparseDrive config differs from preregistration")
    if receiver["model"]["attention_implementation"] != preregistration[
        "receiver"
    ]["attention_implementation"]:
        raise ValueError("SparseDrive attention implementation differs")
    for field in ("frame_stride", "start_frame", "max_frames", "ego_status_mode"):
        if receiver[field] != preregistration["receiver"][field]:
            raise ValueError(f"receiver {field} differs from preregistration")
    if not receiver.get("all_outputs_finite"):
        raise ValueError("receiver contains non-finite native outputs")
    if not receiver.get("all_resets_reproducible"):
        raise ValueError("receiver reset check failed")

    receiver_conditions = {
        item["label"]: item for item in receiver.get("conditions", [])
    }
    if set(receiver_conditions) != set(CONDITIONS):
        raise ValueError("receiver condition labels differ from preregistration")
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        source = (repo / spec["output"]).resolve()
        for name, expected_hash in spec["input_sha256"].items():
            if sha256_file(source / name) != expected_hash:
                raise ValueError(f"{condition}: {name} hash mismatch")
        result = receiver_conditions[condition]
        if Path(result["input"]).resolve() != source:
            raise ValueError(f"{condition}: receiver source mismatch")
        if result["selected_frame_indices"] != preregistration["receiver"][
            "selected_frame_indices"
        ]:
            raise ValueError(f"{condition}: receiver frame indices mismatch")
        if result["ego_status_mode"] != preregistration["receiver"][
            "ego_status_mode"
        ]:
            raise ValueError(f"{condition}: ego-status mode mismatch")

    reference_status = np.asarray(
        [
            item["ego_status_10d"]
            for item in receiver_conditions["slow"]["input_contracts"]
        ]
    )
    reference_commands = np.asarray(
        [
            item["command_one_hot_right_left_straight"]
            for item in receiver_conditions["slow"]["input_contracts"]
        ]
    )
    for condition in CONDITIONS[1:]:
        statuses = np.asarray(
            [
                item["ego_status_10d"]
                for item in receiver_conditions[condition]["input_contracts"]
            ]
        )
        commands = np.asarray(
            [
                item["command_one_hot_right_left_straight"]
                for item in receiver_conditions[condition]["input_contracts"]
            ]
        )
        if not np.array_equal(statuses, reference_status):
            raise ValueError("ego-status values differ across CF-R conditions")
        if not np.array_equal(commands, reference_commands):
            raise ValueError("command values differ across CF-R conditions")
    expected_command = np.asarray(
        preregistration["receiver"]["command_one_hot_right_left_straight"]
    )
    if not np.all(reference_commands == expected_command):
        raise ValueError("receiver command differs from preregistration")

    state_path = (repo / preregistration["state_reference"]["path"]).resolve()
    if sha256_file(state_path) != preregistration["state_reference"]["sha256"]:
        raise ValueError("CF-R state reference hash mismatch")
    state_reference = load_json(state_path)
    if not state_reference["state_forward_order"]["passed"]:
        raise ValueError("reused CF-R forward-state gate failed")
    if not state_reference["state_clearance_order"]["passed"]:
        raise ValueError("reused CF-R clearance-state gate failed")
    return receiver_conditions


def frame_map(condition: dict[str, Any]) -> dict[float, dict[str, Any]]:
    return {float(item["timestamp_s"]): item for item in condition["frames"]}


def analyze_planning_order(
    conditions: dict[str, dict[str, Any]],
    valid_start_s: float,
    valid_end_s: float,
) -> dict[str, Any]:
    by_condition = {
        condition: frame_map(conditions[condition]) for condition in CONDITIONS
    }
    timestamps = sorted(
        timestamp
        for timestamp in by_condition["slow"]
        if valid_start_s <= timestamp <= valid_end_s
    )
    if not timestamps:
        raise ValueError("no receiver frames in the preregistered window")
    rows = []
    for timestamp in timestamps:
        row = {"timestamp_s": timestamp, "conditions": {}}
        for condition in CONDITIONS:
            if timestamp not in by_condition[condition]:
                raise ValueError(f"{condition}: missing timestamp {timestamp}")
            frame = by_condition[condition][timestamp]
            geometry = frame["plan_geometry"]
            row["conditions"][condition] = {
                "final_forward_m": float(geometry["final_forward_m"]),
                "final_right_m": float(geometry["final_right_m"]),
                "first_step_speed_mps": float(geometry["first_step_speed_mps"]),
                "selected_mode_index": int(
                    frame["planning_selection"]["selected_mode_index"]
                ),
            }
        rows.append(row)

    pair_results = {}
    for riskier, safer in PAIRS:
        comparisons = []
        for row in rows:
            riskier_value = row["conditions"][riskier]["final_forward_m"]
            safer_value = row["conditions"][safer]["final_forward_m"]
            margin = safer_value - riskier_value
            comparisons.append(
                {
                    "timestamp_s": row["timestamp_s"],
                    "riskier_final_forward_m": riskier_value,
                    "safer_final_forward_m": safer_value,
                    "margin_m": margin,
                    "outcome": (
                        "expected" if margin > 0.0 else "reversal_or_tie"
                    ),
                }
            )
        pair_results[f"{riskier}<{safer}"] = {
            "riskier": riskier,
            "safer": safer,
            "expected_count": sum(
                item["outcome"] == "expected" for item in comparisons
            ),
            "reversal_or_tie_count": sum(
                item["outcome"] != "expected" for item in comparisons
            ),
            "minimum_margin_m": min(item["margin_m"] for item in comparisons),
            "comparisons": comparisons,
        }

    medians = {
        condition: float(
            np.median(
                [
                    row["conditions"][condition]["final_forward_m"]
                    for row in rows
                ]
            )
        )
        for condition in CONDITIONS
    }
    aggregate_expected = medians["slow"] < medians["nominal"] < medians["fast"]
    reversal_count = sum(
        item["reversal_or_tie_count"] for item in pair_results.values()
    )
    if aggregate_expected and reversal_count == 0:
        decision = "accepted"
    elif aggregate_expected:
        decision = "down-weighted"
    else:
        decision = "rejected"
    mode_switches = {
        condition: sum(
            first["conditions"][condition]["selected_mode_index"]
            != second["conditions"][condition]["selected_mode_index"]
            for first, second in zip(rows[:-1], rows[1:], strict=True)
        )
        for condition in CONDITIONS
    }
    cross_condition_mode_differences = sum(
        len(
            {
                row["conditions"][condition]["selected_mode_index"]
                for condition in CONDITIONS
            }
        )
        > 1
        for row in rows
    )
    return {
        "timestamps_s": timestamps,
        "rows": rows,
        "pair_results": pair_results,
        "median_final_forward_m": medians,
        "aggregate_median_order_expected": aggregate_expected,
        "total_reversal_or_tie_count": reversal_count,
        "planning_direction_decision": decision,
        "mode_diagnostics": {
            "within_condition_mode_switch_counts": mode_switches,
            "timestamps_with_cross_condition_mode_difference": (
                cross_condition_mode_differences
            ),
        },
    }


def save_visualization(analysis: dict[str, Any], output: Path) -> Path:
    import matplotlib.pyplot as plt

    rows = analysis["planning"]["rows"]
    timestamps = [row["timestamp_s"] for row in rows]
    colors = {"slow": "#d62728", "nominal": "#ff7f0e", "fast": "#2ca02c"}
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    forward_axis, margin_axis, mode_axis, lateral_axis = axes.ravel()
    for condition in CONDITIONS:
        forward_axis.plot(
            timestamps,
            [
                row["conditions"][condition]["final_forward_m"]
                for row in rows
            ],
            marker="o",
            color=colors[condition],
            label=condition,
        )
        mode_axis.step(
            timestamps,
            [
                row["conditions"][condition]["selected_mode_index"]
                for row in rows
            ],
            where="mid",
            marker="o",
            color=colors[condition],
            label=condition,
        )
        lateral_axis.plot(
            timestamps,
            [
                row["conditions"][condition]["final_right_m"]
                for row in rows
            ],
            marker="o",
            color=colors[condition],
            label=condition,
        )
    for pair, result in analysis["planning"]["pair_results"].items():
        margin_axis.plot(
            timestamps,
            [item["margin_m"] for item in result["comparisons"]],
            marker="o",
            label=pair,
        )
    margin_axis.axhline(0.0, color="black", linewidth=1)
    forward_axis.set(
        title="Primary metric: 3 s longitudinal plan endpoint",
        xlabel="source time, s",
        ylabel="forward, m",
    )
    margin_axis.set(
        title="Pairwise safer-minus-riskier margins",
        xlabel="source time, s",
        ylabel="margin, m",
    )
    mode_axis.set(
        title="Selected native planning mode",
        xlabel="source time, s",
        ylabel="mode index",
    )
    lateral_axis.set(
        title="Diagnostic only: 3 s lateral endpoint",
        xlabel="source time, s",
        ylabel="right (+) / left (-), m",
    )
    for axis in axes.ravel():
        axis.grid(alpha=0.3)
        axis.legend()
    figure.suptitle(
        "CF-R-PLAN-001: designed conflict order → SparseDrive planning",
        fontsize=15,
    )
    path = output / "cf_r_plan_summary.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    preregistration = load_json(preregistration_path)
    if preregistration["audit_id"] != "hugsim_cf_r_plan_001":
        raise ValueError("unexpected preregistration audit ID")
    preregistration_commit = verify_preregistration(
        repo,
        args.preregistration_commit,
        preregistration_path,
        preregistration,
    )
    receiver_path = args.receiver_report.expanduser().resolve()
    receiver = load_json(receiver_path)
    conditions = verify_inputs(repo, preregistration, receiver)
    window = preregistration["analysis_window"]
    planning = analyze_planning_order(
        conditions,
        float(window["valid_start_inclusive_s"]),
        float(window["valid_end_inclusive_s"]),
    )
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    analysis = {
        "audit_id": preregistration["audit_id"],
        "preregistration_commit": preregistration_commit,
        "receiver_report": str(receiver_path),
        "analysis_window": window,
        "planning": planning,
        "evidence_decisions": {
            "designed_conflict_to_planning_direction": {
                "decision": planning["planning_direction_decision"],
                "claim": preregistration["strongest_allowed_claim"],
            },
            "real_world_safety_or_hugsim_credibility": {
                "decision": "rejected",
                "reason": "scope exceeds this designed internal open-loop experiment",
            },
        },
        "forbidden_claims": preregistration["forbidden_claims"],
    }
    visualization = save_visualization(analysis, output)
    analysis["visualization"] = str(visualization)
    report_path = output / "cf_r_plan_audit.json"
    report_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
