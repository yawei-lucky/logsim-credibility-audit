import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_natural_actor_bridge import (  # noqa: E402
    compare_all_resets,
    interval_decision,
    plan_distance,
    response_decision,
)


class SparseDriveNaturalActorBridgeTest(unittest.TestCase):
    def test_plan_distance_reports_ade_fde_and_signed_endpoint(self):
        first = np.zeros((6, 2))
        second = np.column_stack((np.zeros(6), np.arange(1, 7)))

        result = plan_distance(first, second)

        self.assertEqual(result["ade_m"], 3.5)
        self.assertEqual(result["fde_m"], 6.0)
        self.assertEqual(
            result["final_forward_delta_second_minus_first_m"], 6.0
        )

    def test_all_reset_pairings_are_retained(self):
        zero = np.zeros((6, 2))
        one = np.ones((6, 2))

        result = compare_all_resets([zero, zero], [one, one])

        self.assertEqual(len(result["pairings"]), 4)
        self.assertAlmostEqual(result["ade_m"]["min"], np.sqrt(2))
        self.assertAlmostEqual(result["ade_m"]["max"], np.sqrt(2))

    def test_interval_decision_preserves_reverse_and_overlap(self):
        self.assertEqual(interval_decision(1.0, 2.0, 3.0, 4.0), "accepted")
        self.assertEqual(interval_decision(3.0, 4.0, 1.0, 2.0), "rejected")
        self.assertEqual(
            interval_decision(1.0, 3.0, 2.0, 4.0), "down-weighted"
        )

    def test_response_decision_uses_repeat_envelope(self):
        self.assertEqual(response_decision(2.0, 3.0, 1.0), "accepted")
        self.assertEqual(response_decision(0.2, 0.8, 1.0), "rejected")
        self.assertEqual(
            response_decision(0.8, 1.2, 1.0), "down-weighted"
        )


if __name__ == "__main__":
    unittest.main()
