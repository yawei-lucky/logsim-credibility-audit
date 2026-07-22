import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_hugsim_ordinal_metamorphic import (  # noqa: E402
    geometry_relation,
    receiver_relation,
    relation_evidence_label,
)


def geometry_row(timestamp, forward, left, ego_clearance, corridor_clearance):
    return {
        "timestamp_s": timestamp,
        "actor_forward_m": forward,
        "actor_left_m": left,
        "ego_footprint_clearance_m": ego_clearance,
        "planned_corridor_clearance_m": corridor_clearance,
    }


def receiver_row(timestamp, xy=None):
    association = None
    if xy is not None:
        association = {"prediction_center_vehicle_xy": list(xy)}
    return {
        "timestamp_s": timestamp,
        "actor_matches": [{"nearest_qualified": association}],
    }


class OrdinalMetamorphicAnalysisTest(unittest.TestCase):
    def test_longitudinal_geometry_requires_all_positive_margins(self):
        dominant = [geometry_row(0.25, 10, 0, 5, 3)]
        subordinate = [geometry_row(0.25, 18, 0, 13, 11)]
        result = geometry_relation(dominant, subordinate, "longitudinal")
        self.assertTrue(result["passed"])
        self.assertEqual(result["minimum_factor_margin_m"], 8)

    def test_receiver_counts_unavailable_without_imputation(self):
        dominant = [receiver_row(0.5, (10, 0)), receiver_row(1.0, None)]
        subordinate = [receiver_row(0.5, (20, 0)), receiver_row(1.0, (20, 0))]
        result = receiver_relation(dominant, subordinate, "longitudinal", 1.0)
        self.assertEqual(result["expected_count"], 1)
        self.assertEqual(result["reversal_count"], 0)
        self.assertEqual(result["unavailable_count"], 1)
        self.assertTrue(result["aggregate_direction_expected"])
        self.assertEqual(relation_evidence_label(True, result), "down-weighted")

    def test_receiver_reversal_rejects_aggregate_relation(self):
        dominant = [receiver_row(0.5, (30, 0))]
        subordinate = [receiver_row(0.5, (20, 0))]
        result = receiver_relation(dominant, subordinate, "longitudinal", 1.0)
        self.assertEqual(result["reversal_count"], 1)
        self.assertFalse(result["aggregate_direction_expected"])
        self.assertEqual(relation_evidence_label(True, result), "rejected")


if __name__ == "__main__":
    unittest.main()
