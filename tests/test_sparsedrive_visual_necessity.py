import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_sparsedrive_visual_necessity import (  # noqa: E402
    constant_velocity_reference,
    plan_ade,
    warmed_plan_effect,
)


def run_with_plan(plan: np.ndarray, mode: int = 3) -> dict:
    return {
        "frames": [
            {
                "_final_plan": np.asarray(plan, dtype=np.float32),
                "planning_selection": {"selected_mode_index": mode},
            }
        ]
    }


class SparseDriveVisualNecessityTest(unittest.TestCase):
    def test_warmed_effect_preserves_direction_and_mode(self):
        baseline = np.column_stack((np.zeros(6), np.arange(1.0, 7.0)))
        changed = baseline.copy()
        changed[:, 0] += 0.5
        changed[:, 1] -= 1.0
        result = warmed_plan_effect(
            run_with_plan(baseline, mode=2),
            run_with_plan(changed, mode=3),
        )
        self.assertAlmostEqual(
            result["plan_ade_from_baseline_m"],
            np.sqrt(1.25),
        )
        self.assertEqual(result["final_right_delta_m"], 0.5)
        self.assertEqual(result["final_forward_delta_m"], -1.0)
        self.assertEqual(result["baseline_mode"], 2)
        self.assertEqual(result["condition_mode"], 3)

    def test_constant_velocity_reference_uses_right_and_forward_components(self):
        status = [0.0] * 10
        status[6] = 1.0
        status[7] = 2.0
        reference = constant_velocity_reference(status)
        np.testing.assert_allclose(reference[0], [0.5, 1.0])
        np.testing.assert_allclose(reference[-1], [3.0, 6.0])
        self.assertEqual(plan_ade(reference, reference), 0.0)

    def test_plan_ade_requires_six_two_dimensional_points(self):
        with self.assertRaises(ValueError):
            plan_ade(np.zeros((5, 2)), np.zeros((5, 2)))


if __name__ == "__main__":
    unittest.main()
