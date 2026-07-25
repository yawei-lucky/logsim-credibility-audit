import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_maneuver_conditioned_risk import (  # noqa: E402
    classify_response,
    native_arrays,
    polyline_box_clearance,
    top_two,
)


class SparseDriveManeuverConditionedRiskTest(unittest.TestCase):
    def test_native_arrays_require_the_released_candidate_contract(self):
        output = {
            "planning": np.zeros((3, 6, 6, 2), dtype=float),
            "planning_score": np.zeros((3, 6), dtype=float),
            "final_planning": np.zeros((6, 2), dtype=float),
        }
        planning, scores, final = native_arrays(output)
        self.assertEqual(planning.shape, (3, 6, 6, 2))
        self.assertEqual(scores.shape, (3, 6))
        self.assertEqual(final.shape, (6, 2))
        output["planning"] = np.zeros((3, 5, 6, 2), dtype=float)
        with self.assertRaises(ValueError):
            native_arrays(output)

    def test_classifies_mode_selection_and_true_fixed_mode_reversal(self):
        self.assertEqual(
            classify_response(
                selected_delta_m=1.25,
                candidate_deltas_m=np.asarray(
                    [-0.41, -0.29, -0.37, -0.32, -0.27, -0.29]
                ),
                mode_changed=True,
                selected_repeat_envelope_m=2e-4,
                candidate_repeat_envelope_m=3e-4,
            ),
            "mode_switch_masks_candidate_consensus_less_progress",
        )
        self.assertEqual(
            classify_response(
                selected_delta_m=0.09,
                candidate_deltas_m=np.asarray(
                    [0.22, 0.05, 0.09, 0.23, 0.10, 0.09]
                ),
                mode_changed=False,
                selected_repeat_envelope_m=2e-4,
                candidate_repeat_envelope_m=3e-4,
            ),
            "same_mode_candidate_consensus_more_progress_reversal",
        )

    def test_current_actor_box_clearance_is_spatial_not_temporal(self):
        corners = np.asarray(
            [
                [-1.0, 4.0],
                [1.0, 4.0],
                [1.0, 6.0],
                [-1.0, 6.0],
            ]
        )
        crossing = np.column_stack(
            (np.zeros(6), np.linspace(1.0, 6.0, 6))
        )
        offset = np.column_stack(
            (np.full(6, 3.0), np.linspace(1.0, 6.0, 6))
        )
        self.assertEqual(polyline_box_clearance(crossing, corners), 0.0)
        self.assertAlmostEqual(polyline_box_clearance(offset, corners), 2.0)

    def test_score_margin_retains_runner_up(self):
        result = top_two(np.asarray([0.2, 0.7, 0.4, 0.1, 0.3, 0.6]))
        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], 5)
        self.assertAlmostEqual(result[4], 0.1)


if __name__ == "__main__":
    unittest.main()
