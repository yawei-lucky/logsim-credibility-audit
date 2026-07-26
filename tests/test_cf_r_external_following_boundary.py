import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_cf_r_external_following_boundary import (  # noqa: E402
    evidence_summary,
    minimum_following_distance_m,
    same_lane_relation,
)


SPEEDS = np.asarray([2.0, 2.78, 5.56, 8.33, 11.11, 13.89, 16.67])
TIME_GAPS = np.asarray([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6])


class CfRExternalFollowingBoundaryTest(unittest.TestCase):
    def test_low_speed_floor_and_table_formula(self):
        self.assertEqual(
            minimum_following_distance_m(1.9, SPEEDS, TIME_GAPS),
            2.0,
        )
        self.assertEqual(
            minimum_following_distance_m(2.0, SPEEDS, TIME_GAPS),
            2.0,
        )
        self.assertAlmostEqual(
            minimum_following_distance_m(2.78, SPEEDS, TIME_GAPS),
            2.78 * 1.1,
        )

    def test_speed_above_table_is_unavailable(self):
        self.assertIsNone(
            minimum_following_distance_m(20.0, SPEEDS, TIME_GAPS)
        )

    def test_same_lane_relation_uses_bumper_gap(self):
        ego = [0.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]
        actor = [10.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]

        relation = same_lane_relation(ego, actor)

        self.assertAlmostEqual(relation["longitudinal_bumper_gap_m"], 6.0)
        self.assertAlmostEqual(relation["lateral_overlap_m"], 2.0)
        self.assertTrue(relation["actor_ahead"])
        self.assertTrue(relation["lateral_overlap"])

    def test_one_sided_coverage_is_down_weighted(self):
        rows = [
            {
                "applicable": True,
                "regulatory_margin_m": 1.0,
                "gap_to_minimum_ratio": 1.5,
                "planned_ego_speed_mps": 1.0,
                "heading_difference_rad": 0.0,
                "lateral_overlap_m": 1.0,
            },
            {
                "applicable": True,
                "regulatory_margin_m": 2.0,
                "gap_to_minimum_ratio": 2.0,
                "planned_ego_speed_mps": 2.0,
                "heading_difference_rad": 0.0,
                "lateral_overlap_m": 1.0,
            },
        ]

        summary = evidence_summary(rows)

        self.assertEqual(summary["formula_applicability"], "accepted")
        self.assertEqual(
            summary["every_sample_exceeds_comparator"]["decision"],
            "accepted",
        )
        self.assertEqual(summary["boundary_coverage"]["decision"], "rejected")
        self.assertEqual(summary["overall"], "down-weighted")


if __name__ == "__main__":
    unittest.main()
