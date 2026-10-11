import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_motion_observation_probe import growth_interval, identify_parameters, measure_pair, synthetic_pair

CFG = json.loads((ROOT / "configs/motion_observation_probe_001.json").read_text())


class ProbeMeasurementTests(unittest.TestCase):
    def test_subpixel_measurement_and_missing_marker(self):
        bg = np.full((100, 200, 3), 37, np.uint8)
        pair = synthetic_pair(bg, [(50.3, 50), (130.6, 50)], 1.3, 0.9, [0.9, 0.1])
        self.assertLess(abs(measure_pair(*pair, CFG)["width_px"] - 80.3), 0.5)
        missing = synthetic_pair(bg, [(50.3, 50)], 1.3, 0.9, [0.9, 0.1])
        with self.assertRaises(ValueError):
            measure_pair(*missing, CFG)

    def test_growth_error_bounds_and_invalid_time(self):
        truth = np.log(70 / 50) / 0.5
        for e0 in [-0.5, 0.5]:
            for e1 in [-0.5, 0.5]:
                lo, hi = growth_interval(50 + e0, 70 + e1, 0.5, 0.5)
                self.assertLessEqual(lo, truth)
                self.assertGreaterEqual(hi, truth)
        with self.assertRaises(ValueError):
            growth_interval(50, 70, 0, 0.5)

    def training_rows(self):
        rows = []
        for trajectory in CFG["trajectories"][:2]:
            for t in np.arange(9) * 0.25:
                z = trajectory["z0_m"] - trajectory["closing_speed_mps"] * t
                rows.append({"trajectory": trajectory["id"], "condition": "combined", "repeat": 0,
                             "nominal_depth_m": z,
                             "measurement": {"width_px": 1000 / (z + 1 + trajectory["closing_speed_mps"] * 0.5)}})
        return rows

    def test_two_speeds_identify_and_holdout_cannot_change_fit(self):
        rows = self.training_rows()
        fit = identify_parameters(rows, CFG, 1000)
        self.assertTrue(fit["identified"])
        self.assertAlmostEqual(fit["bias_m"], 1)
        self.assertAlmostEqual(fit["delay_s"], 0.5)
        self.assertLessEqual(fit["bias_interval_m"][0], 1)
        self.assertGreaterEqual(fit["bias_interval_m"][1], 1)
        corrupt_holdout = {**rows[0], "trajectory": "heldout", "measurement": {"width_px": 1e9}}
        self.assertEqual(fit, identify_parameters(rows + [corrupt_holdout], CFG, 1000))

    def test_missing_data_cannot_be_a_success(self):
        rows = self.training_rows()
        rows[0]["measurement"] = None
        self.assertFalse(identify_parameters(rows, CFG, 1000)["identified"])

    def test_nonconstant_bias_invalidates_identification_intersection(self):
        rows = self.training_rows()
        rows[0]["measurement"]["width_px"] *= 1.2
        self.assertFalse(identify_parameters(rows, CFG, 1000)["identified"])


if __name__ == "__main__":
    unittest.main()
