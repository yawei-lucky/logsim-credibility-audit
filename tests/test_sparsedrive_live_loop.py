from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_live_loop import analyze_live_runs  # noqa: E402


def fixtures() -> tuple[dict, dict]:
    info = {"ego_box": [0.0] * 7, "ego_velo": 1.0, "collision": False}
    steps = []
    live = []
    for index in range(2):
        action = {"acc": -0.1, "steer_rate": 0.0}
        steps.extend(
            [
                {
                    "plan_updated": True,
                    "action": action,
                    "terminated": False,
                    "truncated": False,
                    "info_after": info,
                },
                {
                    "plan_updated": False,
                    "action": action,
                    "terminated": False,
                    "truncated": False,
                    "info_after": info,
                },
            ]
        )
        live.append(
            {
                "receiver_timestamp_s": 1.5 + 0.5 * index,
                "observation_rgb_sha256": f"rgb-{index}",
                "native": {
                    "final_planning_values": [[0.0, float(i)] for i in range(6)],
                    "planning_score_values": [
                        [0.0] * 6,
                        [0.0] * 6,
                        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                    ],
                },
                "plan_geometry": {"final_forward_m": 5.0},
            }
        )
    runner = {
        "run_status": "complete",
        "plan_updates_consumed": 2,
        "strict_action_bounds": True,
        "evaluation_skipped": True,
        "steps": steps,
    }
    writer = {
        "status": "complete",
        "requested_plans": 2,
        "plans_sent": 2,
        "done_received": True,
        "exhausted_without_done": False,
        "padding_or_repetition_used": False,
        "first_live_boundary_state_max_abs_residual": 0.0,
        "first_live_boundary_rgb_max_abs_difference": 0,
        "first_plan_reference_max_abs_difference": 1e-5,
        "reset_numerical_envelope": 1e-4,
        "live": live,
    }
    return runner, writer


class SparseDriveLiveLoopTest(unittest.TestCase):
    def test_accepts_live_capability_and_exact_repeat(self) -> None:
        runner, writer = fixtures()

        result = analyze_live_runs(
            runner,
            writer,
            deepcopy(runner),
            deepcopy(writer),
        )

        self.assertEqual(
            result["evidence_decisions"]["live_ad_feedback_capability"][
                "decision"
            ],
            "accepted",
        )
        self.assertEqual(
            result["evidence_decisions"][
                "exact_closed_loop_reset_reproducibility"
            ]["decision"],
            "accepted",
        )

    def test_rejects_exact_repeat_after_feedback_diverges(self) -> None:
        runner, writer = fixtures()
        runner_b, writer_b = deepcopy(runner), deepcopy(writer)
        writer_b["live"][1]["native"]["final_planning_values"][5][1] += 0.01

        result = analyze_live_runs(
            runner,
            writer,
            runner_b,
            writer_b,
        )

        self.assertEqual(
            result["evidence_decisions"][
                "exact_closed_loop_reset_reproducibility"
            ]["decision"],
            "rejected",
        )
        self.assertEqual(
            result["evidence_decisions"]["short_horizon_task_direction_stability"][
                "decision"
            ],
            "down-weighted",
        )


if __name__ == "__main__":
    unittest.main()
