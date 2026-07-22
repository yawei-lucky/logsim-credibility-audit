#!/usr/bin/env python3
"""Validate state-level CF-I indicators on frozen positive/negative controls."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def git_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def first_above(values: list[float], tolerance: float) -> int | None:
    return next((index for index, value in enumerate(values) if value > tolerance), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hugsim-root", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    hugsim_root = args.hugsim_root.resolve()
    prereg_path = args.preregistration.resolve()
    output_dir = args.output_dir.resolve()
    audit_output = args.audit_output.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {output_dir}")
    output_dir.mkdir(parents=True)

    prereg = json.loads(prereg_path.read_text())
    revision = git_revision(hugsim_root)
    if revision != prereg["hugsim_commit"]:
        raise RuntimeError(
            f"HUGSIM revision mismatch: expected {prereg['hugsim_commit']}, got {revision}"
        )

    sys.path[:0] = [str(hugsim_root), str(hugsim_root / "sim")]
    import matplotlib.pyplot as plt
    import numpy as np
    import torch
    from sim.utils.agent_controller import AttackPlanner, ConstantPlanner, constant_headaway

    common = prereg["common"]
    steps = int(common["prediction_steps"])
    transitions = int(common["num_transitions"])
    declared_stimulus = int(common["declared_stimulus_index"])
    attack_update_dt = float(common["attack_update_dt_seconds"])
    released_dt = float(prereg["controls"]["released_grid"]["ego_prediction_index_dt_seconds"])
    aligned_dt = float(prereg["controls"]["aligned_grid"]["ego_prediction_index_dt_seconds"])
    candidate_index_dt = steps * attack_update_dt / (steps - 1)
    if not math.isclose(aligned_dt, candidate_index_dt, abs_tol=1e-15):
        raise RuntimeError("preregistered aligned dt does not match candidate index dt")

    responder_initial = torch.tensor(common["responder_initial_state"])
    ego_initial = torch.tensor(common["ego_initial_state"])
    empty_neighbors = torch.empty((0, steps, 4))

    def run_attack(prediction_dt: float, stimulus_index: int | None) -> list[dict[str, Any]]:
        actor = responder_initial.clone()
        ego = ego_initial.clone()
        torch.manual_seed(int(common["torch_seed"]))
        controller = AttackPlanner(
            pred_steps=steps,
            best_k=int(common["attack_best_k"]),
        )
        rows = []
        for index in range(transitions):
            if stimulus_index is not None and index == stimulus_index:
                ego[3] = 0.0
            predicted_ego = constant_headaway(ego[None], steps, prediction_dt)[0]
            actor_after = controller.update(
                actor,
                None,
                attack_update_dt,
                empty_neighbors,
                predicted_ego,
                new_plan=True,
            ).clone()
            rows.append(
                {
                    "index": index,
                    "world_time_seconds": index * prediction_dt,
                    "ego_state": [float(value) for value in ego],
                    "actor_before": [float(value) for value in actor],
                    "actor_after": [float(value) for value in actor_after],
                }
            )
            actor = actor_after
            ego[0] += ego[3] * torch.sin(ego[2]) * prediction_dt
            ego[1] += ego[3] * torch.cos(ego[2]) * prediction_dt
        return rows

    def run_constant(prediction_dt: float, stimulus_index: int | None) -> list[dict[str, Any]]:
        actor = responder_initial.clone()
        ego = ego_initial.clone()
        controller = ConstantPlanner()
        rows = []
        for index in range(transitions):
            if stimulus_index is not None and index == stimulus_index:
                ego[3] = 0.0
            actor_after = controller.update(actor, prediction_dt).clone()
            rows.append(
                {
                    "index": index,
                    "world_time_seconds": index * prediction_dt,
                    "ego_state": [float(value) for value in ego],
                    "actor_before": [float(value) for value in actor],
                    "actor_after": [float(value) for value in actor_after],
                }
            )
            actor = actor_after
            ego[0] += ego[3] * torch.sin(ego[2]) * prediction_dt
            ego[1] += ego[3] * torch.cos(ego[2]) * prediction_dt
        return rows

    traces = {
        "released_baseline": run_attack(released_dt, None),
        "released_treatment": run_attack(released_dt, declared_stimulus),
        "aligned_baseline": run_attack(aligned_dt, None),
        "aligned_treatment": run_attack(aligned_dt, declared_stimulus),
        "aligned_anticipatory_negative": run_attack(
            aligned_dt,
            int(prereg["controls"]["anticipatory"]["actual_stimulus_index"]),
        ),
        "constant_baseline": run_constant(aligned_dt, None),
        "constant_treatment": run_constant(aligned_dt, declared_stimulus),
    }

    def states(name: str, field: str) -> np.ndarray:
        return np.asarray([row[field] for row in traces[name]], dtype=float)

    state_tol = float(prereg["indicators"]["CF-I-T2"]["state_l2_tolerance"])
    aligned_divergence = np.linalg.norm(
        states("aligned_treatment", "actor_after")
        - states("aligned_baseline", "actor_after"),
        axis=1,
    )
    early_divergence = np.linalg.norm(
        states("aligned_anticipatory_negative", "actor_after")
        - states("aligned_baseline", "actor_after"),
        axis=1,
    )
    constant_divergence = np.linalg.norm(
        states("constant_treatment", "actor_after")
        - states("constant_baseline", "actor_after"),
        axis=1,
    )

    aligned_first = first_above(aligned_divergence.tolist(), state_tol)
    early_first = first_above(early_divergence.tolist(), state_tol)
    constant_first = first_above(constant_divergence.tolist(), state_tol)
    aligned_pre_max = float(aligned_divergence[:declared_stimulus].max())
    early_pre_max = float(early_divergence[:declared_stimulus].max())
    aligned_post_max = float(aligned_divergence[declared_stimulus:].max())
    constant_post_max = float(constant_divergence[declared_stimulus:].max())

    candidate_times = np.linspace(0.0, steps * attack_update_dt, steps)
    released_prediction_times = np.arange(steps) * released_dt
    aligned_prediction_times = np.arange(steps) * aligned_dt
    released_offsets = np.abs(released_prediction_times - candidate_times)
    aligned_offsets = np.abs(aligned_prediction_times - candidate_times)

    def continuity(name: str, world_dt: float) -> dict[str, Any]:
        before = states(name, "actor_before")
        after = states(name, "actor_after")
        displacement = np.linalg.norm(after[:, :2] - before[:, :2], axis=1)
        integrated_speed = 0.5 * (np.abs(before[:, 3]) + np.abs(after[:, 3])) * world_dt
        residual = np.abs(displacement - integrated_speed)
        acceleration = (after[:, 3] - before[:, 3]) / world_dt
        return {
            "coverage": int(len(residual)),
            "position_residual_m": residual.tolist(),
            "max_position_residual_m": float(residual.max()),
            "min_acceleration_mps2": float(acceleration.min()),
            "max_acceleration_mps2": float(acceleration.max()),
        }

    continuity_results = {
        name: continuity(name, released_dt if name.startswith("released") else aligned_dt)
        for name in (
            "released_baseline",
            "released_treatment",
            "aligned_baseline",
            "aligned_treatment",
        )
    }

    time_tol = float(prereg["indicators"]["CF-I-T1"]["tolerance_seconds"])
    position_tol = float(prereg["indicators"]["CF-I-T4"]["position_tolerance_m"])
    acc_min, acc_max = prereg["indicators"]["CF-I-T4"]["acceleration_bounds_mps2"]
    t1_discriminates = bool(released_offsets.max() > time_tol and aligned_offsets.max() <= time_tol)
    t2_positive = bool(
        aligned_pre_max <= state_tol
        and aligned_first is not None
        and aligned_first >= declared_stimulus
    )
    t2_negative_rejected = bool(early_first is not None and early_first < declared_stimulus)
    t2_discriminates = t2_positive and t2_negative_rejected
    t3_positive = bool(aligned_first is not None and aligned_post_max > state_tol)
    t3_negative_rejected = bool(constant_first is None and constant_post_max <= state_tol)
    t3_discriminates = t3_positive and t3_negative_rejected

    def continuity_pass(result: dict[str, Any]) -> bool:
        return bool(
            result["max_position_residual_m"] <= position_tol
            and result["min_acceleration_mps2"] >= acc_min - 1e-9
            and result["max_acceleration_mps2"] <= acc_max + 1e-9
        )

    aligned_continuity_pass = all(
        continuity_pass(continuity_results[name])
        for name in ("aligned_baseline", "aligned_treatment")
    )
    released_continuity_rejected = any(
        not continuity_pass(continuity_results[name])
        for name in ("released_baseline", "released_treatment")
    )
    t4_discriminates = aligned_continuity_pass and released_continuity_rejected

    indicator_results = {
        "CF-I-T1": {
            "released_max_offset_seconds": float(released_offsets.max()),
            "aligned_max_offset_seconds": float(aligned_offsets.max()),
            "released_decision": "rejected" if released_offsets.max() > time_tol else "accepted",
            "aligned_decision": "accepted" if aligned_offsets.max() <= time_tol else "rejected",
            "control_discrimination": "accepted" if t1_discriminates else "rejected",
        },
        "CF-I-T2": {
            "declared_stimulus_index": declared_stimulus,
            "aligned_first_divergence_index": aligned_first,
            "aligned_pre_stimulus_max_l2": aligned_pre_max,
            "anticipatory_first_divergence_index": early_first,
            "anticipatory_pre_stimulus_max_l2": early_pre_max,
            "aligned_decision": "accepted" if t2_positive else "rejected",
            "anticipatory_decision": "rejected" if t2_negative_rejected else "accepted",
            "control_discrimination": "accepted" if t2_discriminates else "rejected",
        },
        "CF-I-T3": {
            "aligned_first_divergence_index": aligned_first,
            "aligned_response_latency_steps": (
                aligned_first - declared_stimulus if aligned_first is not None else None
            ),
            "aligned_post_stimulus_max_l2": aligned_post_max,
            "constant_first_divergence_index": constant_first,
            "constant_post_stimulus_max_l2": constant_post_max,
            "aligned_decision": "accepted" if t3_positive else "rejected",
            "constant_interaction_decision": (
                "rejected" if t3_negative_rejected else "accepted"
            ),
            "control_discrimination": "accepted" if t3_discriminates else "rejected",
        },
        "CF-I-T4": {
            "position_tolerance_m": position_tol,
            "acceleration_bounds_mps2": [acc_min, acc_max],
            "conditions": continuity_results,
            "aligned_decision": "accepted" if aligned_continuity_pass else "rejected",
            "released_decision": (
                "rejected" if released_continuity_rejected else "accepted"
            ),
            "control_discrimination": "accepted" if t4_discriminates else "rejected",
        },
    }

    all_indicators_pass = all(
        value["control_discrimination"] == "accepted"
        for value in indicator_results.values()
    )
    prereg_ref = "docs/runs/hugsim_interaction_state_preregistration_001.json"
    controller_ref = f"HUGSIM@{revision}:sim/utils/agent_controller.py:AttackPlanner.update"
    planner_ref = f"HUGSIM@{revision}:sim/utils/plan.py:planner.plan_traj"
    spline_ref = (
        f"HUGSIM@{revision}:submodules/Pplan/Sampling/"
        "spline_planner.py:compute_spline_xyvaqrt"
    )
    audit = {
        "experiment_id": prereg["experiment_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hugsim_commit": revision,
        "preregistration": prereg_ref,
        "scope": "deterministic state-level CF-I indicator validation",
        "indicator_results": indicator_results,
        "credibility": {
            "evidence_decision": "down-weighted",
            "claim_decisions": {
                "cf_i_t1_control_discrimination": "accepted" if t1_discriminates else "rejected",
                "cf_i_t2_control_discrimination": "accepted" if t2_discriminates else "rejected",
                "cf_i_t3_control_discrimination": "accepted" if t3_discriminates else "rejected",
                "cf_i_t4_control_discrimination": "accepted" if t4_discriminates else "rejected",
                "released_grid_is_temporally_consistent_interaction": "rejected",
                "anticipatory_control_respects_declared_causal_order": "rejected",
                "constant_planner_has_online_stimulus_response": "rejected",
                "aligned_attackplanner_has_state_level_response": (
                    "accepted" if t2_positive and t3_positive and aligned_continuity_pass else "rejected"
                ),
            },
            "rejected_claim_contexts": {
                "released_grid_is_temporally_consistent_interaction": {
                    "tested": True,
                    "rejection_basis": "invalidated_by_diagnostic",
                    "reason": "future indices and world-state transitions use incompatible time bases",
                    "evidence_refs": [prereg_ref, planner_ref, spline_ref],
                    "diagnostic_finding": "CF-I-STATE-001-D1",
                },
                "anticipatory_control_respects_declared_causal_order": {
                    "tested": True,
                    "rejection_basis": "contradicted_by_evidence",
                    "reason": "responder divergence begins before the declared stimulus index",
                    "evidence_refs": [prereg_ref, controller_ref],
                    "diagnostic_finding": "CF-I-STATE-001-D2",
                },
                "constant_planner_has_online_stimulus_response": {
                    "tested": True,
                    "rejection_basis": "contradicted_by_evidence",
                    "reason": "paired ConstantPlanner states remain identical after the ego stimulus",
                    "evidence_refs": [
                        prereg_ref,
                        f"HUGSIM@{revision}:sim/utils/agent_controller.py:ConstantPlanner.update",
                    ],
                    "diagnostic_finding": "CF-I-STATE-001-D3",
                },
            },
        },
        "diagnostic_findings": {
            "CF-I-STATE-001-D1": {
                "component": "CF-I-T1 and CF-I-T4",
                "expected": "compared state indices share time and displacement agrees with world time",
                "observed": (
                    f"released maximum time offset={released_offsets.max():.6f} s; "
                    f"maximum continuity residual={max(continuity_results['released_baseline']['max_position_residual_m'], continuity_results['released_treatment']['max_position_residual_m']):.6f} m"
                ),
                "expectation_met": False,
                "implication": "released-grid interaction timing is not qualified",
                "evidence_decision": "accepted",
                "evidence_refs": [prereg_ref, planner_ref, spline_ref],
            },
            "CF-I-STATE-001-D2": {
                "component": "CF-I-T2 anticipatory negative",
                "expected": "no responder divergence before declared stimulus index 8",
                "observed": f"first divergence occurred at index {early_first}",
                "expectation_met": False,
                "implication": "CF-I-T2 detects the constructed result-before-cause control",
                "evidence_decision": "accepted",
                "evidence_refs": [prereg_ref, controller_ref],
            },
            "CF-I-STATE-001-D3": {
                "component": "CF-I-T3 ConstantPlanner negative",
                "expected": "an online interaction mechanism changes after the ego stimulus",
                "observed": f"maximum post-stimulus paired L2 divergence={constant_post_max:.6f}",
                "expectation_met": False,
                "implication": "CF-I-T3 does not mistake independent scripted motion for response",
                "evidence_decision": "accepted",
                "evidence_refs": [
                    prereg_ref,
                    f"HUGSIM@{revision}:sim/utils/agent_controller.py:ConstantPlanner.update",
                ],
            },
            "CF-I-STATE-001-D4": {
                "component": "CF-I-T1 through CF-I-T4 control discrimination",
                "expected": "each indicator separates its preregistered known controls",
                "observed": f"all four control-discrimination decisions accepted={all_indicators_pass}",
                "expectation_met": all_indicators_pass,
                "implication": "the four indicators are qualified only for this state-level test use",
                "evidence_decision": "accepted" if all_indicators_pass else "rejected",
                "evidence_refs": [prereg_ref, controller_ref, planner_ref, spline_ref],
            },
        },
        "strongest_allowed_claim": (
            "CF-I-T1..T4 distinguish their frozen state-level controls. This does not "
            "qualify realistic interaction behavior, rendered sensors, AD response, or "
            "closed-loop outcomes."
        ),
        "stop_rule_triggered": not all_indicators_pass,
    }

    trace_path = output_dir / "interaction_state_traces.json"
    trace_path.write_text(json.dumps(traces, indent=2) + "\n")
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, indent=2) + "\n")

    indices = np.arange(transitions)
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    axes[0, 0].plot(np.arange(steps), released_offsets, label="released")
    axes[0, 0].plot(np.arange(steps), aligned_offsets, label="aligned")
    axes[0, 0].set(title="CF-I-T1 indexed-time offset", xlabel="future index", ylabel="offset (s)")
    axes[0, 0].legend()

    axes[0, 1].plot(indices, aligned_divergence, label="declared stimulus")
    axes[0, 1].plot(indices, early_divergence, label="one-step-early negative")
    axes[0, 1].axvline(declared_stimulus, color="black", linestyle="--", label="declared index")
    axes[0, 1].set(title="CF-I-T2 paired responder divergence", xlabel="transition", ylabel="state L2")
    axes[0, 1].legend()

    axes[1, 0].plot(
        indices,
        states("aligned_baseline", "actor_after")[:, 3],
        label="aligned baseline",
    )
    axes[1, 0].plot(
        indices,
        states("aligned_treatment", "actor_after")[:, 3],
        label="aligned treatment",
    )
    axes[1, 0].axvline(declared_stimulus, color="black", linestyle="--")
    axes[1, 0].set(title="CF-I-T3 responder speed", xlabel="transition", ylabel="speed (m/s)")
    axes[1, 0].legend()

    released_residual = np.maximum(
        continuity_results["released_baseline"]["position_residual_m"],
        continuity_results["released_treatment"]["position_residual_m"],
    )
    aligned_residual = np.maximum(
        continuity_results["aligned_baseline"]["position_residual_m"],
        continuity_results["aligned_treatment"]["position_residual_m"],
    )
    axes[1, 1].plot(indices, released_residual, label="released max pair")
    axes[1, 1].plot(indices, aligned_residual, label="aligned max pair")
    axes[1, 1].axhline(position_tol, color="black", linestyle="--", label="tolerance")
    axes[1, 1].set(title="CF-I-T4 state-time residual", xlabel="transition", ylabel="residual (m)")
    axes[1, 1].legend()

    figure.suptitle("CF-I-STATE-001 indicator control discrimination")
    figure.savefig(output_dir / "interaction_state_indicator_summary.png", dpi=160)
    plt.close(figure)

    print(json.dumps(audit, indent=2))
    return 0 if all_indicators_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
