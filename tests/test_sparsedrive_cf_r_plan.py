import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_sparsedrive_cf_r_plan import analyze_planning_order  # noqa: E402


def condition(values: list[float], modes: list[int] | None = None) -> dict:
    if modes is None:
        modes = [0] * len(values)
    return {
        "frames": [
            {
                "timestamp_s": 1.5 + 0.5 * index,
                "plan_geometry": {
                    "final_forward_m": value,
                    "final_right_m": 0.0,
                    "first_step_speed_mps": 2.0,
                },
                "planning_selection": {"selected_mode_index": mode},
            }
            for index, (value, mode) in enumerate(zip(values, modes, strict=True))
        ]
    }


class SparseDriveCFRPlanTest(unittest.TestCase):
    def test_accepts_strict_expected_order(self):
        result = analyze_planning_order(
            {
                "slow": condition([4.0, 4.1]),
                "nominal": condition([5.0, 5.1]),
                "fast": condition([6.0, 6.1]),
            },
            1.5,
            2.0,
        )

        self.assertEqual(result["planning_direction_decision"], "accepted")
        self.assertEqual(result["total_reversal_or_tie_count"], 0)

    def test_down_weights_frame_reversal_when_median_order_survives(self):
        result = analyze_planning_order(
            {
                "slow": condition([5.2, 4.0, 4.0]),
                "nominal": condition([5.0, 5.0, 5.0]),
                "fast": condition([6.0, 6.0, 6.0]),
            },
            1.5,
            2.5,
        )

        self.assertEqual(result["planning_direction_decision"], "down-weighted")
        self.assertGreater(result["total_reversal_or_tie_count"], 0)

    def test_rejects_aggregate_median_reversal(self):
        result = analyze_planning_order(
            {
                "slow": condition([7.0, 7.0]),
                "nominal": condition([5.0, 5.0]),
                "fast": condition([6.0, 6.0]),
            },
            1.5,
            2.0,
        )

        self.assertEqual(result["planning_direction_decision"], "rejected")

    def test_reports_mode_switches_as_diagnostic(self):
        result = analyze_planning_order(
            {
                "slow": condition([4.0, 4.1], [0, 1]),
                "nominal": condition([5.0, 5.1], [0, 0]),
                "fast": condition([6.0, 6.1], [0, 0]),
            },
            1.5,
            2.0,
        )

        self.assertEqual(
            result["mode_diagnostics"]["within_condition_mode_switch_counts"][
                "slow"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
