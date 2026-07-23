from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_cf_r_closed_loop import (  # noqa: E402
    longitudinal_progress,
    robust_expected_order,
)


class SparseDriveCFRClosedLoopTest(unittest.TestCase):
    def test_longitudinal_progress_uses_boundary_heading(self) -> None:
        boundary = [1.0, 2.0, 0.0, 1.6, 3.0, 1.5, 0.0]
        current = [4.0, 2.5, 0.0, 1.6, 3.0, 1.5, 0.0]

        self.assertAlmostEqual(
            longitudinal_progress(boundary, current),
            3.0,
        )

    def test_accepts_effect_larger_than_repeat_variation(self) -> None:
        result = robust_expected_order(
            [3.00, 3.01],
            [3.50, 3.52],
        )

        self.assertEqual(result["decision"], "accepted")
        self.assertTrue(result["effect_exceeds_repeat_variation"])

    def test_down_weights_direction_smaller_than_repeat_variation(self) -> None:
        result = robust_expected_order(
            [3.00, 3.20],
            [3.25, 3.30],
        )

        self.assertEqual(result["decision"], "down-weighted")
        self.assertTrue(result["direction_passed"])

    def test_rejects_a_pairwise_reversal(self) -> None:
        result = robust_expected_order(
            [3.00, 3.40],
            [3.50, 3.30],
        )

        self.assertEqual(result["decision"], "rejected")
        self.assertFalse(result["direction_passed"])


if __name__ == "__main__":
    unittest.main()
