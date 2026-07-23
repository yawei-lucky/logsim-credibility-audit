from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_plan_to_loop import analyze_contract  # noqa: E402


def fixture() -> tuple:
    plan = np.stack((np.zeros(6), np.arange(1, 7)), axis=1)
    info = {
        "ego_box": [0.0] * 7,
        "ego_pos": [0.0] * 3,
        "ego_rot": [0.0] * 3,
        "ego_velo": 1.0,
        "ego_steer": 0.0,
    }
    action = {"acc": -0.4, "steer_rate": 0.02}
    first_after = {
        **info,
        "ego_velo": 0.9,
        "ego_steer": 0.005,
        "collision": False,
    }
    second_before = deepcopy(first_after)
    second_after = {
        **second_before,
        "ego_velo": 0.8,
        "ego_steer": 0.01,
        "collision": False,
    }
    steps = [
        {
            "plan_updated": True,
            "control_hold_substep": 0,
            "info_before": info,
            "info_after": first_after,
            "plan_traj": plan.tolist(),
            "action": action,
            "terminated": False,
            "truncated": False,
        },
        {
            "plan_updated": False,
            "control_hold_substep": 1,
            "info_before": second_before,
            "info_after": second_after,
            "plan_traj": plan.tolist(),
            "action": action,
            "terminated": False,
            "truncated": False,
        },
    ]
    run = {
        "run_status": "complete",
        "completed_steps": 2,
        "plan_updates_consumed": 1,
        "control_hold_steps": 2,
        "strict_action_bounds": True,
        "evaluation_skipped": True,
        "control_convention": "corrected",
        "steps": steps,
    }
    writer = {
        "status": "complete",
        "responses_sent": 1,
        "done_received": True,
        "exhausted_without_done": False,
        "padding_or_repetition_used": False,
    }
    return plan, info, run, writer


class SparseDrivePlanToLoopTest(unittest.TestCase):
    def test_accepts_exact_two_substep_handoff(self) -> None:
        plan, info, run, writer = fixture()

        result = analyze_contract(
            plan,
            info,
            run,
            writer,
            deepcopy(run),
            deepcopy(writer),
            0.25,
        )

        self.assertEqual(
            result["evidence_decisions"]["frozen_plan_to_loop_capability"][
                "decision"
            ],
            "accepted",
        )
        self.assertTrue(all(result["gates"].values()))

    def test_rejects_silent_plan_change(self) -> None:
        plan, info, run, writer = fixture()
        run["steps"][0]["plan_traj"][0][1] = 99.0

        result = analyze_contract(
            plan,
            info,
            run,
            writer,
            deepcopy(run),
            deepcopy(writer),
            0.25,
        )

        self.assertEqual(
            result["evidence_decisions"]["frozen_plan_to_loop_capability"][
                "decision"
            ],
            "rejected",
        )
        self.assertFalse(result["gates"]["native_plan_identity_preserved"])


if __name__ == "__main__":
    unittest.main()
