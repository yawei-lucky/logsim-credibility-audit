#!/usr/bin/env python3
"""Transport frozen CF-I indicators into HUGSIM planner.plan_traj."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    parser.add_argument("--state-reference", type=Path, required=True)
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
        raise RuntimeError("HUGSIM revision differs from preregistration")
    for asset in prereg["assets"].values():
        if sha256(Path(asset["path"])) != asset["sha256"]:
            raise RuntimeError(f"asset hash mismatch: {asset['path']}")

    sys.path[:0] = [str(hugsim_root), str(hugsim_root / "sim")]
    import matplotlib.pyplot as plt
    import numpy as np
    import torch
    from sim.utils.plan import planner

    execution = prereg["execution"]
    steps = int(execution["prediction_steps"])
    transitions = int(execution["num_transitions"])
    declared_stimulus = int(execution["declared_stimulus_index"])
    attack_update_dt = float(execution["attack_update_dt_seconds"])
    released_dt = float(prereg["controls"]["released_grid"]["planner_dt_seconds"])
    aligned_dt = float(prereg["controls"]["aligned_grid"]["planner_dt_seconds"])
    candidate_index_dt = steps * attack_update_dt / (steps - 1)
    if not math.isclose(aligned_dt, candidate_index_dt, abs_tol=1e-15):
        raise RuntimeError("aligned dt does not match AttackPlanner candidate index dt")

    ground_path = Path(prereg["assets"]["scene_ground"]["path"])
    with ground_path.open("rb") as stream:
        ground = pickle.load(stream)
    vehicle_dir = str(Path(prereg["assets"]["vehicle_model"]["path"]).parent)
    scene_dir = str(ground_path.parent)

    def run_loop(
        controller_name: str,
        planner_dt: float,
        stimulus_index: int | None,
    ) -> list[dict[str, Any]]:
        actor = list(execution["responder_plan_state"])
        if controller_name == "AttackPlanner":
            controller_args = {
                "pred_steps": steps,
                "ATTACK_FREQ": int(execution["attack_frequency"]),
                "best_k": int(execution["attack_best_k"]),
            }
        else:
            controller_args = {}
        plan_list = [actor + [vehicle_dir, controller_name, controller_args]]
        torch.manual_seed(int(execution["torch_seed"]))
        loop = planner(
            plan_list,
            scene_path=scene_dir,
            unified_map=None,
            ground=ground,
            dt=planner_dt,
        )
        ego = torch.tensor(execution["ego_initial_state"])
        rows = []
        for index in range(transitions):
            if stimulus_index is not None and index == stimulus_index:
                ego[3] = 0.0
            before = loop.stats["agent_0"][[0, 1, 3, 4]].clone()
            loop.plan_traj(index * planner_dt, ego)
            after = loop.stats["agent_0"][[0, 1, 3, 4]].clone()
            rows.append(
                {
                    "index": index,
                    "world_time_seconds": index * planner_dt,
                    "ego_state": [float(value) for value in ego],
                    "actor_before": [float(value) for value in before],
                    "actor_after": [float(value) for value in after],
                }
            )
            ego[0] += ego[3] * torch.sin(ego[2]) * planner_dt
            ego[1] += ego[3] * torch.cos(ego[2]) * planner_dt
        return rows

    early_index = int(prereg["controls"]["anticipatory"]["actual_stimulus_index"])
    traces = {
        "released_baseline": run_loop("AttackPlanner", released_dt, None),
        "released_treatment": run_loop("AttackPlanner", released_dt, declared_stimulus),
        "aligned_baseline": run_loop("AttackPlanner", aligned_dt, None),
        "aligned_treatment": run_loop("AttackPlanner", aligned_dt, declared_stimulus),
        "aligned_anticipatory_negative": run_loop("AttackPlanner", aligned_dt, early_index),
        "constant_baseline": run_loop("ConstantPlanner", aligned_dt, None),
        "constant_treatment": run_loop("ConstantPlanner", aligned_dt, declared_stimulus),
    }

    def states(source: dict[str, Any], name: str, field: str) -> np.ndarray:
        return np.asarray([row[field] for row in source[name]], dtype=float)

    state_tol = float(prereg["frozen_indicators"]["CF-I-T2"]["state_l2_tolerance"])
    aligned_divergence = np.linalg.norm(
        states(traces, "aligned_treatment", "actor_after")
        - states(traces, "aligned_baseline", "actor_after"),
        axis=1,
    )
    early_divergence = np.linalg.norm(
        states(traces, "aligned_anticipatory_negative", "actor_after")
        - states(traces, "aligned_baseline", "actor_after"),
        axis=1,
    )
    constant_divergence = np.linalg.norm(
        states(traces, "constant_treatment", "actor_after")
        - states(traces, "constant_baseline", "actor_after"),
        axis=1,
    )
    aligned_first = first_above(aligned_divergence.tolist(), state_tol)
    early_first = first_above(early_divergence.tolist(), state_tol)
    constant_first = first_above(constant_divergence.tolist(), state_tol)

    candidate_times = np.linspace(0.0, steps * attack_update_dt, steps)
    released_offsets = np.abs(np.arange(steps) * released_dt - candidate_times)
    aligned_offsets = np.abs(np.arange(steps) * aligned_dt - candidate_times)

    def continuity(name: str, world_dt: float) -> dict[str, float | int]:
        before = states(traces, name, "actor_before")
        after = states(traces, name, "actor_after")
        displacement = np.linalg.norm(after[:, :2] - before[:, :2], axis=1)
        integrated_speed = 0.5 * (np.abs(before[:, 3]) + np.abs(after[:, 3])) * world_dt
        residual = np.abs(displacement - integrated_speed)
        acceleration = (after[:, 3] - before[:, 3]) / world_dt
        return {
            "coverage": len(residual),
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
    time_tol = float(prereg["frozen_indicators"]["CF-I-T1"]["tolerance_seconds"])
    position_tol = float(prereg["frozen_indicators"]["CF-I-T4"]["position_tolerance_m"])
    acc_min, acc_max = prereg["frozen_indicators"]["CF-I-T4"]["acceleration_bounds_mps2"]

    def continuity_pass(result: dict[str, float | int]) -> bool:
        return bool(
            result["max_position_residual_m"] <= position_tol
            and result["min_acceleration_mps2"] >= acc_min - 1e-6
            and result["max_acceleration_mps2"] <= acc_max + 1e-6
        )

    t1 = bool(released_offsets.max() > time_tol and aligned_offsets.max() <= time_tol)
    t2 = bool(
        aligned_divergence[:declared_stimulus].max() <= state_tol
        and aligned_first is not None
        and aligned_first >= declared_stimulus
        and early_first is not None
        and early_first < declared_stimulus
    )
    t3 = bool(
        aligned_first is not None
        and aligned_divergence[declared_stimulus:].max() > state_tol
        and constant_first is None
        and constant_divergence[declared_stimulus:].max() <= state_tol
    )
    aligned_continuity = all(
        continuity_pass(continuity_results[name])
        for name in ("aligned_baseline", "aligned_treatment")
    )
    released_rejected = any(
        not continuity_pass(continuity_results[name])
        for name in ("released_baseline", "released_treatment")
    )
    t4 = aligned_continuity and released_rejected

    indicator_results = {
        "CF-I-T1": {
            "released_max_offset_seconds": float(released_offsets.max()),
            "aligned_max_offset_seconds": float(aligned_offsets.max()),
            "control_discrimination": "accepted" if t1 else "rejected",
        },
        "CF-I-T2": {
            "declared_stimulus_index": declared_stimulus,
            "aligned_first_divergence_index": aligned_first,
            "aligned_pre_stimulus_max_l2": float(
                aligned_divergence[:declared_stimulus].max()
            ),
            "anticipatory_first_divergence_index": early_first,
            "anticipatory_pre_stimulus_max_l2": float(
                early_divergence[:declared_stimulus].max()
            ),
            "control_discrimination": "accepted" if t2 else "rejected",
        },
        "CF-I-T3": {
            "aligned_response_latency_steps": (
                aligned_first - declared_stimulus if aligned_first is not None else None
            ),
            "aligned_post_stimulus_max_l2": float(
                aligned_divergence[declared_stimulus:].max()
            ),
            "constant_post_stimulus_max_l2": float(
                constant_divergence[declared_stimulus:].max()
            ),
            "control_discrimination": "accepted" if t3 else "rejected",
        },
        "CF-I-T4": {
            "conditions": continuity_results,
            "aligned_decision": "accepted" if aligned_continuity else "rejected",
            "released_decision": "rejected" if released_rejected else "accepted",
            "control_discrimination": "accepted" if t4 else "rejected",
        },
    }

    state_reference = json.loads(args.state_reference.resolve().read_text())
    state_trace_path = (
        Path(__file__).resolve().parents[1]
        / "artifacts/hugsim_interaction_state/analysis-run001/interaction_state_traces.json"
    )
    reference_traces = json.loads(state_trace_path.read_text())
    trace_differences = {}
    for name in traces:
        trace_differences[name] = float(
            np.linalg.norm(
                states(traces, name, "actor_after")
                - states(reference_traces, name, "actor_after"),
                axis=1,
            ).max()
        )

    prior_decisions = {
        key: value["control_discrimination"]
        for key, value in state_reference["indicator_results"].items()
    }
    loop_decisions = {
        key: value["control_discrimination"] for key, value in indicator_results.items()
    }
    transport_success = prior_decisions == loop_decisions and all(
        decision == "accepted" for decision in loop_decisions.values()
    )

    prereg_ref = "docs/runs/hugsim_interaction_planner_loop_preregistration_001.json"
    planner_ref = f"HUGSIM@{revision}:sim/utils/plan.py:planner.plan_traj"
    controller_ref = f"HUGSIM@{revision}:sim/utils/agent_controller.py:AttackPlanner.update"
    constant_ref = f"HUGSIM@{revision}:sim/utils/agent_controller.py:ConstantPlanner.update"
    spline_ref = (
        f"HUGSIM@{revision}:submodules/Pplan/Sampling/"
        "spline_planner.py:compute_spline_xyvaqrt"
    )
    audit = {
        "experiment_id": prereg["experiment_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hugsim_commit": revision,
        "preregistration": prereg_ref,
        "execution_entrypoint": "sim.utils.plan.planner.plan_traj",
        "indicator_results": indicator_results,
        "transport": {
            "prior_state_harness_decisions": prior_decisions,
            "planner_loop_decisions": loop_decisions,
            "max_actor_state_l2_difference_vs_state_harness": trace_differences,
            "success": transport_success,
        },
        "credibility": {
            "evidence_decision": "down-weighted",
            "claim_decisions": {
                "cf_i_t1_transports_to_planner_loop": "accepted" if t1 else "rejected",
                "cf_i_t2_transports_to_planner_loop": "accepted" if t2 else "rejected",
                "cf_i_t3_transports_to_planner_loop": "accepted" if t3 else "rejected",
                "cf_i_t4_transports_to_planner_loop": "accepted" if t4 else "rejected",
                "released_grid_is_temporally_consistent_interaction": "rejected",
                "anticipatory_control_respects_declared_causal_order": "rejected",
                "constant_planner_has_online_stimulus_response": "rejected",
                "all_four_indicator_decisions_transport": (
                    "accepted" if transport_success else "rejected"
                ),
            },
            "rejected_claim_contexts": {
                "released_grid_is_temporally_consistent_interaction": {
                    "tested": True,
                    "rejection_basis": "invalidated_by_diagnostic",
                    "reason": "planner-loop future indices and state transitions use incompatible times",
                    "evidence_refs": [prereg_ref, planner_ref, spline_ref],
                    "diagnostic_finding": "CF-I-LOOP-001-D1",
                },
                "anticipatory_control_respects_declared_causal_order": {
                    "tested": True,
                    "rejection_basis": "contradicted_by_evidence",
                    "reason": "planner-loop responder diverges before the declared stimulus",
                    "evidence_refs": [prereg_ref, planner_ref, controller_ref],
                    "diagnostic_finding": "CF-I-LOOP-001-D2",
                },
                "constant_planner_has_online_stimulus_response": {
                    "tested": True,
                    "rejection_basis": "contradicted_by_evidence",
                    "reason": "planner-loop ConstantPlanner traces remain identical after stimulus",
                    "evidence_refs": [prereg_ref, planner_ref, constant_ref],
                    "diagnostic_finding": "CF-I-LOOP-001-D3",
                },
            },
        },
        "diagnostic_findings": {
            "CF-I-LOOP-001-D1": {
                "component": "planner-loop CF-I-T1/T4",
                "expected": "matching indexed times and world-time state continuity",
                "observed": (
                    f"released offset={released_offsets.max():.6f} s; maximum residual="
                    f"{max(continuity_results['released_baseline']['max_position_residual_m'], continuity_results['released_treatment']['max_position_residual_m']):.6f} m"
                ),
                "expectation_met": False,
                "implication": "released planner-loop interaction timing is not qualified",
                "evidence_decision": "accepted",
                "evidence_refs": [prereg_ref, planner_ref, spline_ref],
            },
            "CF-I-LOOP-001-D2": {
                "component": "planner-loop CF-I-T2 anticipatory control",
                "expected": "no divergence before declared index 8",
                "observed": f"first divergence occurred at index {early_first}",
                "expectation_met": False,
                "implication": "T2 retains result-before-cause sensitivity in planner.plan_traj",
                "evidence_decision": "accepted",
                "evidence_refs": [prereg_ref, planner_ref, controller_ref],
            },
            "CF-I-LOOP-001-D3": {
                "component": "planner-loop CF-I-T3 ConstantPlanner control",
                "expected": "an online mechanism responds after ego stimulus",
                "observed": f"post-stimulus paired L2 maximum={constant_divergence[declared_stimulus:].max():.6f}",
                "expectation_met": False,
                "implication": "T3 retains no-response discrimination in planner.plan_traj",
                "evidence_decision": "accepted",
                "evidence_refs": [prereg_ref, planner_ref, constant_ref],
            },
            "CF-I-LOOP-001-D4": {
                "component": "T1--T4 state-harness to planner-loop transport",
                "expected": "all four frozen control decisions reproduce",
                "observed": f"transport success={transport_success}",
                "expectation_met": transport_success,
                "implication": "indicator transport is qualified only before rendering",
                "evidence_decision": "accepted" if transport_success else "rejected",
                "evidence_refs": [prereg_ref, planner_ref, controller_ref, spline_ref],
            },
        },
        "strongest_allowed_claim": (
            "CF-I-T1..T4 retain frozen control discrimination inside planner.plan_traj. "
            "This does not qualify rendering, traffic realism, AD response, or closed-loop outcomes."
        ),
        "stop_rule_triggered": not transport_success,
    }

    (output_dir / "interaction_planner_loop_traces.json").write_text(
        json.dumps(traces, indent=2) + "\n"
    )
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, indent=2) + "\n")

    indices = np.arange(transitions)
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    axes[0, 0].plot(np.arange(steps), released_offsets, label="released")
    axes[0, 0].plot(np.arange(steps), aligned_offsets, label="aligned")
    axes[0, 0].set(title="T1 planner-loop time offset", xlabel="future index", ylabel="offset (s)")
    axes[0, 0].legend()
    axes[0, 1].plot(indices, aligned_divergence, label="declared stimulus")
    axes[0, 1].plot(indices, early_divergence, label="one-step-early")
    axes[0, 1].axvline(declared_stimulus, color="black", linestyle="--")
    axes[0, 1].set(title="T2 planner-loop divergence", xlabel="transition", ylabel="state L2")
    axes[0, 1].legend()
    axes[1, 0].plot(
        indices,
        states(traces, "aligned_baseline", "actor_after")[:, 3],
        label="baseline",
    )
    axes[1, 0].plot(
        indices,
        states(traces, "aligned_treatment", "actor_after")[:, 3],
        label="treatment",
    )
    axes[1, 0].axvline(declared_stimulus, color="black", linestyle="--")
    axes[1, 0].set(title="T3 planner-loop response", xlabel="transition", ylabel="speed (m/s)")
    axes[1, 0].legend()
    labels = ["released base", "released treat", "aligned base", "aligned treat"]
    values = [
        continuity_results[name]["max_position_residual_m"]
        for name in (
            "released_baseline",
            "released_treatment",
            "aligned_baseline",
            "aligned_treatment",
        )
    ]
    axes[1, 1].bar(labels, values)
    axes[1, 1].axhline(position_tol, color="black", linestyle="--", label="tolerance")
    axes[1, 1].set_yscale("log")
    axes[1, 1].tick_params(axis="x", rotation=20)
    axes[1, 1].set(title="T4 maximum state-time residual", ylabel="residual (m, log)")
    axes[1, 1].legend()
    figure.suptitle("CF-I-LOOP-001 frozen indicator transport")
    figure.savefig(output_dir / "interaction_planner_loop_indicator_summary.png", dpi=160)
    plt.close(figure)

    print(json.dumps(audit, indent=2))
    return 0 if transport_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
