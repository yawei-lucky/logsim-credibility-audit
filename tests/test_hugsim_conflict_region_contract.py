import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_hugsim_conflict_region_contract import (  # noqa: E402
    classify_boolean_occupancy,
    local_conflict_region,
    signed_occupancy_gap,
)


class HugsimConflictRegionContractTest(unittest.TestCase):
    def test_single_complete_intervals_produce_signed_gap(self):
        times = np.arange(7, dtype=float)
        ego = classify_boolean_occupancy(times, [0, 1, 1, 0, 0, 0, 0])
        actor = classify_boolean_occupancy(times, [0, 0, 0, 1, 1, 0, 0])
        self.assertEqual(ego["category"], "single_complete_interval")
        self.assertEqual(signed_occupancy_gap(ego, actor), 1.0)

    def test_overlap_is_negative(self):
        times = np.arange(7, dtype=float)
        ego = classify_boolean_occupancy(times, [0, 1, 1, 1, 0, 0, 0])
        actor = classify_boolean_occupancy(times, [0, 0, 1, 1, 1, 0, 0])
        self.assertEqual(signed_occupancy_gap(ego, actor), -1.0)

    def test_special_branches_fail_closed(self):
        times = np.arange(8, dtype=float)
        multiple = classify_boolean_occupancy(
            times, [0, 1, 0, 0, 1, 0, 0, 0]
        )
        censored = classify_boolean_occupancy(
            times, [1, 1, 0, 0, 0, 0, 0, 0]
        )
        avoided = classify_boolean_occupancy(
            times, np.zeros(8), spatial_avoidance_known=True
        )
        after = classify_boolean_occupancy(
            times, np.zeros(8), enters_after_horizon_known=True
        )
        unknown = classify_boolean_occupancy(times, np.zeros(8))
        self.assertEqual(multiple["category"], "multiple_intervals")
        self.assertEqual(censored["category"], "censored_left")
        self.assertEqual(avoided["category"], "spatial_avoidance")
        self.assertEqual(after["category"], "after_horizon")
        self.assertEqual(unknown["category"], "no_occupancy_unresolved")
        self.assertIsNone(signed_occupancy_gap(multiple, after))

    def test_local_corridors_create_finite_polygon(self):
        ego = np.column_stack([np.linspace(-10, 10, 21), np.zeros(21)])
        region = local_conflict_region(
            ego,
            np.asarray([0.0, 0.0]),
            actor_heading_deg=0.0,
            ego_width_m=2.0,
            actor_width_m=2.0,
            local_half_length_m=5.0,
        )
        self.assertGreater(region.area, 0.0)


if __name__ == "__main__":
    unittest.main()
