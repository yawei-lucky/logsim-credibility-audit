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
    from sim.utils.agent_controller import (
        AttackPlanner,
        ConstantPlanner,
        IDM,
        UnicyclePlanner,
    )

    torch.manual_seed(0)
    dt = 0.2
    initial_state = torch.tensor([0.0, 0.0, 0.0, 5.0])

    # IDM: move the same synthetic neighbor from off-path to a close lead-car
    # position while holding the responder state and route fixed.
    route = torch.stack(
        [torch.tensor([0.0, float(y), 0.0]) for y in range(51)]
    )
    far_neighbor = torch.tensor([[[10.0, 10.0, 0.0, 0.0]] * 20])
    close_lead = torch.tensor([[[0.0, 6.0, 0.0, 0.0]] * 20])
    idm_far = IDM().update(initial_state, route, dt, far_neighbor)
    idm_close = IDM().update(initial_state, route, dt, close_lead)

    # AttackPlanner: both ego plans start at the same lateral position; one
    # remains straight and one progressively moves laterally.  The actor's
    # initial state and all other inputs stay fixed.
    time = torch.arange(20) * dt
    ego_plan_straight = torch.stack(
        [
            torch.zeros(20),
            5.0 + 5.0 * time,
            torch.zeros(20),
            torch.full((20,), 5.0),
        ],
        dim=-1,
    )
    ego_plan_lateral = ego_plan_straight.clone()
    ego_plan_lateral[:, 0] = torch.linspace(0.0, 5.0, 20)
    no_other_neighbors = torch.empty((0, 20, 4))

    torch.manual_seed(0)
    attack_straight = AttackPlanner(best_k=1).update(
        initial_state,
        None,
        dt,
        no_other_neighbors,
        ego_plan_straight,
    )
    torch.manual_seed(0)
    attack_lateral = AttackPlanner(best_k=1).update(
        initial_state,
        None,
        dt,
        no_other_neighbors,
        ego_plan_lateral,
    )

    idm_speed_delta = float(idm_close[3] - idm_far[3])
    attack_response_delta = attack_lateral - attack_straight
    attack_response_l2 = float(torch.linalg.vector_norm(attack_response_delta))
    idm_responded = bool(idm_close[3] < idm_far[3])
    attack_responded = bool(attack_response_l2 > 1e-6)

    source_path = hugsim_root / "sim" / "utils" / "agent_controller.py"
    planner_source_path = hugsim_root / "sim" / "utils" / "plan.py"
    result = {
        "audit_id": "CF-I-CAP-001",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "controller-level internal stimulus-response capability",
        "hugsim": {
            "root": str(hugsim_root),
            "revision": _git_revision(hugsim_root),
            "controller_source": str(source_path),
            "controller_source_sha256": _sha256(source_path),
            "planner_source": str(planner_source_path),
            "planner_source_sha256": _sha256(planner_source_path),
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
            "attack_ego_future_plan": {
                "held_fixed": ["actor initial state", "dt", "candidate generator", "other neighbors"],
                "stimulus": "ego future plan changed from straight to progressive 5 m lateral shift",
                "straight_output": [float(v) for v in attack_straight],
                "lateral_output": [float(v) for v in attack_lateral],
                "response_delta": [float(v) for v in attack_response_delta],
                "response_l2": attack_response_l2,
                "response_detected": attack_responded,
            },
        },
        "judgments": {
            "two_independent_constant_planners_are_interaction": "rejected",
            "idm_has_internal_neighbor_stimulus_response": "accepted" if idm_responded else "rejected",
            "attack_planner_has_internal_ego_plan_stimulus_response": "accepted" if attack_responded else "rejected",
            "overall_evidence": "down-weighted",
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
        },
        "claim_boundary": (
            "The code contains controller-level vehicle stimulus-response mechanisms. "
            "This does not establish realistic traffic behavior, scene-level causal timing, "
            "sensor credibility, AD response, or real-world fitness."
        ),
    }

    if not (idm_responded and attack_responded):
        result["capability_gate"] = "failed"
        exit_code = 1
    else:
        result["capability_gate"] = "passed_for_internal_mechanism_only"
        exit_code = 0

    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
