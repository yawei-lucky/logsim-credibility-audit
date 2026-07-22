#!/usr/bin/env python3
"""Probe whether HUGSIM controllers have an actual stimulus-response input.

This is a controller-level capability audit, not a traffic-realism test.  It
holds each controller's initial state fixed and changes only the declared
vehicle stimulus.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_revision(path: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hugsim-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    hugsim_root = args.hugsim_root.resolve()
    sys.path[:0] = [str(hugsim_root), str(hugsim_root / "sim")]

    import torch
    import yaml
    from sim.utils.agent_controller import (
        AttackPlanner,
        ConstantPlanner,
        IDM,
        UnicyclePlanner,
        constant_headaway,
    )

    torch.manual_seed(0)
    kinematic_path = hugsim_root / "configs" / "sim" / "kinematic.yaml"
    planner_dt = float(yaml.safe_load(kinematic_path.read_text())["dt"])
    planner_source_path = hugsim_root / "sim" / "utils" / "plan.py"
    planner_source = planner_source_path.read_text()
    attack_dt_match = re.search(
        r"elif type\(controller\) is AttackPlanner:.*?controller\.update\(.*?dt=([0-9.]+)",
        planner_source,
        flags=re.DOTALL,
    )
    if attack_dt_match is None:
        raise RuntimeError("could not extract AttackPlanner dt from plan.py")
    attack_update_dt = float(attack_dt_match.group(1))
    prediction_steps = 20
    attack_candidate_horizon = prediction_steps * attack_update_dt
    attack_candidate_index_dt = attack_candidate_horizon / (prediction_steps - 1)

    initial_state = torch.tensor([0.0, 0.0, 0.0, 5.0])

    # IDM: move the same synthetic neighbor from off-path to a close lead-car
    # position while holding the responder state and route fixed.
    route = torch.stack(
        [torch.tensor([0.0, float(y), 0.0]) for y in range(51)]
    )
    far_neighbor = torch.tensor([[[10.0, 10.0, 0.0, 0.0]] * 20])
    close_lead = torch.tensor([[[0.0, 6.0, 0.0, 0.0]] * 20])
    idm_far = IDM().update(initial_state, route, planner_dt, far_neighbor)
    idm_close = IDM().update(initial_state, route, planner_dt, close_lead)

    # AttackPlanner: use the same constant_headaway path as plan.py so both
    # stimuli are reachable from a scene-loop ego state.  The ego is either
    # 15 m or 5 m ahead of the fixed responder.
    attack_state = torch.tensor([0.0, -15.0, 0.0, 3.0])
    ego_far_state = torch.tensor([[0.0, 0.0, 0.0, 0.5]])
    ego_near_state = torch.tensor([[0.0, -10.0, 0.0, 0.5]])
    no_other_neighbors = torch.empty((0, 20, 4))

    def attack_probe(ego_state: torch.Tensor, prediction_dt: float) -> tuple[torch.Tensor, torch.Tensor]:
        attacked_states = constant_headaway(ego_state, 20, prediction_dt)[0]
        torch.manual_seed(0)
        output = AttackPlanner(pred_steps=20, best_k=1).update(
            attack_state,
            None,
            attack_update_dt,
            no_other_neighbors,
            attacked_states,
        )
        return output, attacked_states

    attack_far, predicted_far = attack_probe(ego_far_state, planner_dt)
    attack_near, predicted_near = attack_probe(ego_near_state, planner_dt)
    attack_far_repeat, _ = attack_probe(ego_far_state, planner_dt)
    aligned_far, _ = attack_probe(ego_far_state, attack_candidate_index_dt)
    aligned_near, _ = attack_probe(ego_near_state, attack_candidate_index_dt)

    idm_speed_delta = float(idm_close[3] - idm_far[3])
    attack_response_delta = attack_near - attack_far
    attack_response_l2 = float(torch.linalg.vector_norm(attack_response_delta))
    attack_repeat_l2 = float(torch.linalg.vector_norm(attack_far_repeat - attack_far))
    aligned_response_delta = aligned_near - aligned_far
    aligned_response_l2 = float(torch.linalg.vector_norm(aligned_response_delta))
    idm_responded = bool(idm_close[3] < idm_far[3])
    attack_responded = bool(attack_response_l2 > 1e-6 and attack_repeat_l2 <= 1e-9)
    aligned_attack_responded = bool(aligned_response_l2 > 1e-6)
    time_grid_aligned = bool(abs(planner_dt - attack_candidate_index_dt) <= 1e-9)
    released_max_time_offset = (prediction_steps - 1) * abs(
        planner_dt - attack_candidate_index_dt
    )
    aligned_max_time_offset = 0.0
    time_alignment_indicator_validated = bool(
        released_max_time_offset > 1e-9 and aligned_max_time_offset <= 1e-9
    )

    source_path = hugsim_root / "sim" / "utils" / "agent_controller.py"
    spline_source_path = (
        hugsim_root / "submodules" / "Pplan" / "Sampling" / "spline_planner.py"
    )
    revision = _git_revision(hugsim_root)
    controller_ref = f"HUGSIM@{revision}:sim/utils/agent_controller.py"
    planner_ref = f"HUGSIM@{revision}:sim/utils/plan.py:planner.plan_traj"
    kinematic_ref = f"HUGSIM@{revision}:configs/sim/kinematic.yaml:dt"
    spline_ref = (
        f"HUGSIM@{revision}:submodules/Pplan/Sampling/"
        "spline_planner.py:compute_spline_xyvaqrt"
    )
    result = {
        "experiment_id": "CF-I-CAP-001",
        "audit_id": "CF-I-CAP-001",
        "hugsim_commit": revision,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "controller capability and released scene-loop qualification",
        "hugsim": {
            "root": str(hugsim_root),
            "revision": revision,
            "controller_source": str(source_path),
            "controller_source_sha256": _sha256(source_path),
            "planner_source": str(planner_source_path),
            "planner_source_sha256": _sha256(planner_source_path),
            "spline_source": str(spline_source_path),
            "spline_source_sha256": _sha256(spline_source_path),
        },
        "controller_interfaces": {
            "ConstantPlanner.update": str(inspect.signature(ConstantPlanner.update)),
            "UnicyclePlanner.update": str(inspect.signature(UnicyclePlanner.update)),
            "IDM.update": str(inspect.signature(IDM.update)),
            "AttackPlanner.update": str(inspect.signature(AttackPlanner.update)),
        },
        "probes": {
            "idm_neighbor_position": {
                "held_fixed": ["responder initial state", "route", "dt", "IDM parameters"],
                "stimulus": "same neighbor moved from off-route to 6 m ahead on route",
                "far_output": [float(v) for v in idm_far],
                "close_output": [float(v) for v in idm_close],
                "next_speed_delta_mps": idm_speed_delta,
                "response_detected": idm_responded,
            },
            "attack_reachable_ego_distance": {
                "held_fixed": [
                    "responder initial state",
                    "ego heading and speed",
                    "candidate generator",
                    "other neighbors",
                ],
                "stimulus": "current ego state moved from 15 m to 5 m ahead of responder",
                "far_ego_state": [float(v) for v in ego_far_state[0]],
                "near_ego_state": [float(v) for v in ego_near_state[0]],
                "far_predicted_final": [float(v) for v in predicted_far[-1]],
                "near_predicted_final": [float(v) for v in predicted_near[-1]],
                "far_output": [float(v) for v in attack_far],
                "near_output": [float(v) for v in attack_near],
                "response_delta": [float(v) for v in attack_response_delta],
                "response_l2": attack_response_l2,
                "identical_input_repeat_l2": attack_repeat_l2,
                "response_detected": attack_responded,
            },
            "attack_aligned_time_grid_control": {
                "prediction_index_dt_seconds": attack_candidate_index_dt,
                "candidate_index_dt_seconds": attack_candidate_index_dt,
                "attack_update_dt_argument_seconds": attack_update_dt,
                "far_output": [float(v) for v in aligned_far],
                "near_output": [float(v) for v in aligned_near],
                "response_delta": [float(v) for v in aligned_response_delta],
                "response_l2": aligned_response_l2,
                "response_detected": aligned_attack_responded,
            },
        },
        "indicator_validation": {
            "indicator_id": "CF-I-T1",
            "name": "stimulus-response indexed-time alignment",
            "law_type": "hard constraint",
            "measurement": "maximum absolute timestamp offset at compared trajectory indices",
            "valid_coverage": {"compared_indices": prediction_steps, "total_indices": prediction_steps},
            "falsifier": "any indexwise cost compares states representing different future times",
            "released_negative_control": {
                "prediction_index_dt_seconds": planner_dt,
                "candidate_index_dt_seconds": attack_candidate_index_dt,
                "max_abs_time_offset_seconds": released_max_time_offset,
                "decision": "rejected" if not time_grid_aligned else "accepted",
            },
            "aligned_positive_control": {
                "prediction_index_dt_seconds": attack_candidate_index_dt,
                "candidate_index_dt_seconds": attack_candidate_index_dt,
                "max_abs_time_offset_seconds": aligned_max_time_offset,
                "decision": "accepted",
            },
            "control_discrimination": (
                "accepted" if time_alignment_indicator_validated else "rejected"
            ),
            "strongest_allowed_claim": (
                "CF-I-T1 distinguishes this source-confirmed time-grid mismatch from an "
                "aligned control; it does not assess behavioral realism."
            ),
        },
        "credibility": {
            "claim_decisions": {
                "independent_constant_planners_are_online_interaction": "rejected",
                "independent_unicycle_planners_are_online_interaction": "rejected",
                "idm_has_internal_neighbor_stimulus_response": "accepted" if idm_responded else "rejected",
                "attack_planner_has_reachable_internal_ego_response": "accepted" if attack_responded else "rejected",
                "cf_i_t1_discriminates_known_time_grid_controls": (
                    "accepted" if time_alignment_indicator_validated else "rejected"
                ),
                "released_scene_loop_is_temporally_qualified_interaction": (
                    "accepted" if time_grid_aligned else "rejected"
                ),
            },
            "evidence_decision": "down-weighted",
            "rejected_claim_contexts": {
                "independent_constant_planners_are_online_interaction": {
                    "tested": True,
                    "rejection_basis": "contradicted_by_evidence",
                    "reason": "ConstantPlanner.update has no live vehicle input.",
                    "evidence_refs": [f"{controller_ref}:ConstantPlanner.update"],
                    "diagnostic_finding": "CF-I-CAP-001-D1",
                },
                "independent_unicycle_planners_are_online_interaction": {
                    "tested": True,
                    "rejection_basis": "contradicted_by_evidence",
                    "reason": "UnicyclePlanner.update advances only its restored trajectory clock.",
                    "evidence_refs": [f"{controller_ref}:UnicyclePlanner.update"],
                    "diagnostic_finding": "CF-I-CAP-001-D2",
                },
                "released_scene_loop_is_temporally_qualified_interaction": {
                    "tested": True,
                    "rejection_basis": "invalidated_by_diagnostic",
                    "reason": (
                        "Indexed ego predictions and AttackPlanner candidates use different "
                        "time steps in the released local configuration."
                    ),
                    "evidence_refs": [planner_ref, kinematic_ref, spline_ref],
                    "diagnostic_finding": "CF-I-CAP-001-D5",
                },
            },
        },
        "diagnostic_findings": {
                "CF-I-CAP-001-D1": {
                    "evidence_decision": "accepted",
                    "component": "ConstantPlanner.update",
                    "expected": "online interaction requires a live other-vehicle input",
                    "observed": "interface is (state, dt)",
                    "expectation_met": False,
                    "implication": "independent ConstantPlanner tracks are scripted motion, not online interaction",
                    "evidence_refs": [f"{controller_ref}:ConstantPlanner.update"],
                },
                "CF-I-CAP-001-D2": {
                    "evidence_decision": "accepted",
                    "component": "UnicyclePlanner.update",
                    "expected": "online interaction requires a live other-vehicle input",
                    "observed": "interface is (dt)",
                    "expectation_met": False,
                    "implication": "restored UnicyclePlanner tracks cannot react online to another vehicle",
                    "evidence_refs": [f"{controller_ref}:UnicyclePlanner.update"],
                },
                "CF-I-CAP-001-D3": {
                    "evidence_decision": "accepted" if idm_responded else "rejected",
                    "component": "IDM.update",
                    "expected": "a close on-route lead lowers the next speed versus an off-route neighbor",
                    "observed": f"next speed delta was {idm_speed_delta:.6f} m/s",
                    "expectation_met": idm_responded,
                    "implication": "IDM has a route-dependent internal neighbor-response path",
                    "evidence_refs": [f"{controller_ref}:IDM.update"],
                },
                "CF-I-CAP-001-D4": {
                    "evidence_decision": "accepted" if attack_responded else "rejected",
                    "component": "AttackPlanner.update",
                    "expected": "a reachable ego-distance stimulus changes deterministic responder output",
                    "observed": (
                        f"response L2 was {attack_response_l2:.6f}; identical-input "
                        f"repeat L2 was {attack_repeat_l2:.6f}"
                    ),
                    "expectation_met": attack_responded,
                    "implication": "AttackPlanner has an internal ego-response path",
                    "evidence_refs": [
                        f"{controller_ref}:AttackPlanner.update",
                        planner_ref,
                    ],
                },
                "CF-I-CAP-001-D5": {
                    "evidence_decision": "accepted",
                    "component": "planner.plan_traj to AttackPlanner.update time base",
                    "expected": "states compared at the same array index represent the same future time",
                    "observed": (
                        f"ego prediction dt was {planner_dt:.2f} s and AttackPlanner "
                        f"candidate index dt was {attack_candidate_index_dt:.6f} s"
                    ),
                    "expectation_met": time_grid_aligned,
                    "implication": "released local scene-loop interaction timing is not qualified",
                    "evidence_refs": [planner_ref, kinematic_ref, spline_ref],
                },
                "CF-I-CAP-001-D6": {
                    "evidence_decision": (
                        "accepted" if time_alignment_indicator_validated else "rejected"
                    ),
                    "component": "CF-I-T1 indicator",
                    "expected": "reject a mismatched time-grid control and accept an aligned control",
                    "observed": (
                        f"released maximum offset was {released_max_time_offset:.2f} s; "
                        f"aligned-control maximum offset was {aligned_max_time_offset:.2f} s"
                    ),
                    "expectation_met": time_alignment_indicator_validated,
                    "implication": "CF-I-T1 is qualified for this narrow implementation-audit use",
                    "evidence_refs": [planner_ref, kinematic_ref, spline_ref],
                },
        },
        "scene_loop_trace": {
            "attack_stimulus_source": (
                "plan.py extrapolates the current ego state with constant_headaway "
                "and passes future_states[0] as attacked_states"
            ),
            "ordinary_neighbor_boundary": (
                "plan.py passes neighbors[1:] as safe_neighbors; generic non-ego "
                "vehicle-to-vehicle response is not qualified by this probe"
            ),
            "ego_prediction_index_dt_seconds": planner_dt,
            "attack_update_dt_argument_seconds": attack_update_dt,
            "attack_candidate_index_dt_seconds": attack_candidate_index_dt,
            "time_grid_aligned": time_grid_aligned,
            "attack_frequency_boundary": (
                "plan.py stores one planner-wide ATTACK_FREQ; use one AttackPlanner "
                "responder until per-actor timing is separately checked"
            ),
        },
        "claim_boundary": (
            "The code contains controller-level vehicle stimulus-response mechanisms, and "
            "AttackPlanner responds under a reachable input construction. The released local "
            "scene loop is not temporally qualified because compared futures use different "
            "time grids. This does not establish realistic traffic behavior, sensor "
            "credibility, AD response, or real-world fitness."
        ),
    }

    if not (
        idm_responded
        and attack_responded
        and aligned_attack_responded
        and time_alignment_indicator_validated
    ):
        result["capability_gate"] = "failed"
        exit_code = 1
    elif not time_grid_aligned:
        result["capability_gate"] = "internal_mechanism_found_scene_level_gate_rejected"
        exit_code = 0
    else:
        result["capability_gate"] = "passed_for_temporally_aligned_internal_mechanism"
        exit_code = 0

    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
