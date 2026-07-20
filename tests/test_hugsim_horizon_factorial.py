import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_hugsim_horizon_factorial import (  # noqa: E402
    factorial_effects,
    valid_window_summary,
)
from analyze_hugsim_near_cutin import interpolated_zero_crossing  # noqa: E402


class HorizonFactorialAnalysisTest(unittest.TestCase):
    def test_valid_window_excludes_tail_failures(self):
        result = {
            "details": {
                "0.25": {
                    "nc": 1.0,
                    "dac": 1.0,
                    "ttc": 1.0,
                    "c": 1.0,
                    "pdms": 1.0,
                },
                "0.5": {
                    "nc": 0.0,
                    "dac": 1.0,
                    "ttc": 0.0,
                    "c": 1.0,
                    "pdms": 0.0,
                },
            }
        }

        summary = valid_window_summary(result, cutoff_s=0.25)

        self.assertEqual(summary["frame_count"], 1)
        self.assertEqual(summary["mean_metrics"]["nc"], 1.0)
        self.assertIsNone(summary["first_failure_s"]["ttc"])

    def test_factorial_interaction_is_zero_when_lead_has_no_effect(self):
        metrics = {
            "no_actor": {metric: 1.0 for metric in ("nc", "dac", "ttc", "c", "pdms")},
            "lead_only": {metric: 1.0 for metric in ("nc", "dac", "ttc", "c", "pdms")},
            "cut_in_only": {metric: 0.5 for metric in ("nc", "dac", "ttc", "c", "pdms")},
            "lead_and_cut_in": {metric: 0.5 for metric in ("nc", "dac", "ttc", "c", "pdms")},
        }

        effects = factorial_effects(metrics)

        self.assertEqual(effects["ttc"]["lead_without_cut_in"], 0.0)
        self.assertEqual(effects["ttc"]["cut_in_without_lead"], -0.5)
        self.assertEqual(effects["ttc"]["interaction"], 0.0)

    def test_interpolated_zero_crossing(self):
        crossing = interpolated_zero_crossing(
            [3.75, 4.0],
            [-0.16, 0.08],
        )

        self.assertAlmostEqual(crossing, 3.9166666667)


if __name__ == "__main__":
    unittest.main()
