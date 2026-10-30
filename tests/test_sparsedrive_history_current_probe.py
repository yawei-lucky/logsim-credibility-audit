import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_sparsedrive_history_current_probe import ARMS, contrast, domain_for, records


class HistoryCurrentProbeTests(unittest.TestCase):
    def plans(self, values):
        return {a: np.full((2, 6, 2), v, dtype=float) for a, v in values.items()}

    def test_only_final_frame_changes_within_same_history(self):
        frames = [12, 18, 24, 30, 36, 42, 48, 54]
        self.assertEqual([domain_for("RS", f, 54) for f in frames], ["R"] * 7 + ["S"])
        self.assertEqual([domain_for("SR", f, 54) for f in frames], ["S"] * 7 + ["R"])
        for arm in ARMS:
            self.assertEqual(domain_for(arm, 54, 54), arm[1])
        with self.assertRaises(ValueError):
            domain_for("bad", 54, 54)

    def test_additive_and_interacting_receivers_are_distinguished(self):
        coefficients = {"SS": 1, "SR": -1, "RS": -1, "RR": 1}
        additive = self.plans({"RR": 1, "RS": 3, "SR": 4, "SS": 6})
        self.assertFalse(contrast(additive, coefficients, 1e-4)["numerically_resolved_nonzero"])
        additive["SS"] += 0.01
        result = contrast(additive, coefficients, 1e-4)
        self.assertTrue(result["numerically_resolved_nonzero"])
        self.assertAlmostEqual(result["max_coordinate_distance_from_zero_m"], 0.0096)

    def test_total_cancellation_does_not_hide_conditional_effects(self):
        plans = self.plans({"RR": 0, "RS": 1, "SR": -1, "SS": 0})
        self.assertFalse(contrast(plans, {"SS": 1, "RR": -1}, 1e-4)["numerically_resolved_nonzero"])
        self.assertTrue(contrast(plans, {"SR": 1, "RR": -1}, 1e-4)["numerically_resolved_nonzero"])
        self.assertTrue(contrast(plans, {"RS": 1, "RR": -1}, 1e-4)["numerically_resolved_nonzero"])

    def test_replicate_spread_prevents_false_detection(self):
        plans = self.plans({"RR": 0, "RS": 0.001, "SR": 0, "SS": 0})
        plans["RS"][0] = -0.001
        self.assertFalse(contrast(plans, {"RS": 1, "RR": -1}, 1e-4)["numerically_resolved_nonzero"])

    def test_guard_propagates_to_all_four_terms(self):
        plans = self.plans({"RR": 0, "RS": 0, "SR": 0, "SS": 0.0003})
        self.assertFalse(contrast(plans, {"SS": 1, "SR": -1, "RS": -1, "RR": 1}, 1e-4)["numerically_resolved_nonzero"])
        with self.assertRaises(ValueError):
            bad = {**plans, "SS": np.full((2, 6, 2), np.nan)}
            contrast(bad, {"SS": 1, "RR": -1}, 1e-4)

    def test_camera_completeness_does_not_silently_accept_duplicates(self):
        metadata = {"frames": [{"rgb_path": "images/CAM_FRONT/00012.jpg"}] * 2}
        with self.assertRaises(ValueError):
            records(metadata, 12)


if __name__ == "__main__":
    unittest.main()
