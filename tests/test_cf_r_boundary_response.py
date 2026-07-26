import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_cf_r_boundary_response import (  # noqa: E402
    ACTION_PATTERN,
    conflict_rows,
)


def state(timestamp, ego_x=0.0, actor_x=10.0):
    return {
        "timestamp": timestamp,
        "ego_box": [ego_x, 0.0, 0.0, 1.6, 3.0, 1.5, 0.0],
        "obj_boxes": [
            [actor_x, 0.0, 0.0, 1.6, 3.6, 1.5, 0.0]
        ],
    }


class CfRBoundaryResponseTest(unittest.TestCase):
    def test_strict_action_failure_is_parseable(self):
        match = ACTION_PATTERN.search(
            "ValueError: steer_rate=0.4 is outside HUGSIM action bounds "
            "[-0.2617993877991494, 0.2617993877991494]"
        )
        self.assertIsNotNone(match)
        self.assertEqual(float(match.group("value")), 0.4)
        self.assertAlmostEqual(float(match.group("upper")), np.pi / 12)

    def test_common_plan_remains_applicable(self):
        timeline = {
            round(float(timestamp), 9): state(timestamp, actor_x=10 + 0.5 * timestamp)
            for timestamp in np.arange(1.5, 4.5 + 0.125, 0.25)
        }
        plan = np.stack(
            [np.zeros(6), np.arange(1, 7) * 0.5],
            axis=1,
        )
        rows = conflict_rows(plan, timeline)
        self.assertTrue(all(row["applicable"] for row in rows))

    def test_near_stop_heading_can_invalidate_same_lane_gate(self):
        timeline = {
            round(float(timestamp), 9): state(timestamp)
            for timestamp in np.arange(1.5, 4.5 + 0.125, 0.25)
        }
        plan = np.asarray(
            [
                [0.0, 0.5],
                [0.0, 1.0],
                [0.0, 1.5],
                [0.0, 2.0],
                [0.0, 2.5],
                [0.01, 2.51],
            ]
        )
        rows = conflict_rows(plan, timeline)
        self.assertTrue(all(row["applicable"] for row in rows[:-1]))
        self.assertFalse(rows[-1]["applicable"])


if __name__ == "__main__":
    unittest.main()
