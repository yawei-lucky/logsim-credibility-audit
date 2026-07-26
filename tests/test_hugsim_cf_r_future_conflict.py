import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_hugsim_cf_r_future_conflict import (  # noqa: E402
    constant_speed_plan,
    expected_order_decision,
    state_timeline,
    world_boxes_from_plan,
)


class HugsimCfRFutureConflictTest(unittest.TestCase):
    def test_world_mapping_uses_right_forward_contract(self):
        origin = [10.0, 5.0, 0.0, 2.0, 4.0, 1.5, 0.0]
        plan = np.asarray(
            [
                [1.0, 2.0],
                [1.0, 4.0],
                [1.0, 6.0],
                [1.0, 8.0],
                [1.0, 10.0],
                [1.0, 12.0],
            ]
        )

        boxes = world_boxes_from_plan(plan, origin)

        self.assertEqual(boxes[0][:2], [12.0, 4.0])
        self.assertAlmostEqual(boxes[-1][0], 22.0)
        self.assertAlmostEqual(boxes[-1][1], 4.0)

    def test_constant_speed_plan_has_declared_horizon(self):
        plan = constant_speed_plan(2.0)

        np.testing.assert_allclose(plan[:, 0], 0.0)
        np.testing.assert_allclose(plan[:, 1], [1, 2, 3, 4, 5, 6])

    def test_expected_order_requires_effect_beyond_repeat(self):
        accepted = expected_order_decision([1.0, 1.1], [2.0, 2.1])
        down_weighted = expected_order_decision([1.0, 1.5], [1.6, 2.0])
        rejected = expected_order_decision([2.0, 2.0], [1.0, 1.0])

        self.assertEqual(accepted["decision"], "accepted")
        self.assertEqual(down_weighted["decision"], "down-weighted")
        self.assertEqual(rejected["decision"], "rejected")

    def test_state_timeline_rejects_discontinuity(self):
        def state(timestamp, x):
            return {
                "timestamp": timestamp,
                "ego_box": [x, 0, 0, 2, 4, 1.5, 0],
                "obj_boxes": [[10, 0, 0, 2, 4, 1.5, 0]],
                "ego_velo": 1.0,
            }

        audit = {
            "steps": [
                {
                    "info_before": state(1.5, 0.0),
                    "info_after": state(1.75, 0.25),
                },
                {
                    "info_before": state(1.75, 9.0),
                    "info_after": state(2.0, 0.5),
                },
            ]
        }

        with self.assertRaisesRegex(ValueError, "state discontinuity"):
            state_timeline(audit)


if __name__ == "__main__":
    unittest.main()
