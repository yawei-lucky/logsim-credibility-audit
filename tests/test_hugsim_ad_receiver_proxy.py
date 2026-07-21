import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_hugsim_ad_receiver_proxy import (  # noqa: E402
    causal_checks,
    receiver_features,
    summarize_series,
)


class HugsimAdReceiverProxyTest(unittest.TestCase):
    def test_receiver_features_are_zero_without_vehicle_mask(self):
        observation = {
            "semantic": {"CAM_FRONT": np.zeros((4, 5), dtype=np.uint8)},
            "depth": {"CAM_FRONT": np.full((4, 5), 10.0, dtype=np.float32)},
        }

        features = receiver_features(observation, "CAM_FRONT", 13)

        self.assertEqual(features["vehicle_component_count"], 0)
        self.assertEqual(features["top_hazard_proxy"], 0.0)
        self.assertIsNone(features["top_median_depth_m"])

    def test_summarize_series_records_visibility_and_peak(self):
        rows = [
            {
                "timestamp_s": 0.0,
                "visible_vehicle_area_fraction": 0.0,
                "center_vehicle_area_fraction": 0.0,
                "top_hazard_proxy": 0.0,
                "top_median_depth_m": None,
                "vehicle_component_count": 0,
            },
            {
                "timestamp_s": 0.25,
                "visible_vehicle_area_fraction": 0.01,
                "center_vehicle_area_fraction": 0.005,
                "top_hazard_proxy": 2.0,
                "top_median_depth_m": 8.0,
                "vehicle_component_count": 1,
            },
        ]

        summary = summarize_series(rows)

        self.assertEqual(summary["visible_frame_count"], 1)
        self.assertEqual(summary["first_visible_s"], 0.25)
        self.assertEqual(summary["peak_hazard_proxy"], 2.0)
        self.assertEqual(summary["minimum_top_median_depth_m"], 8.0)

    def test_causal_checks_accept_expected_direction(self):
        summaries = {
            "front_far": {
                "peak_hazard_proxy": 5.0,
                "minimum_top_median_depth_m": 12.0,
                "maximum_vehicle_component_count": 1,
            },
            "front_near": {
                "peak_hazard_proxy": 10.0,
                "minimum_top_median_depth_m": 4.0,
                "peak_center_vehicle_area_fraction": 0.05,
            },
            "adjacent_near": {
                "peak_hazard_proxy": 6.0,
                "peak_center_vehicle_area_fraction": 0.0,
            },
            "multicar_merge": {
                "peak_hazard_proxy": 20.0,
                "maximum_vehicle_component_count": 3,
            },
        }

        decisions = {
            check["id"]: check["decision"]
            for check in causal_checks(summaries)
        }

        self.assertEqual(
            decisions["distance_response_front_near_vs_far"],
            "accepted",
        )
        self.assertEqual(
            decisions["lane_relation_response_front_vs_adjacent"],
            "accepted",
        )
        self.assertEqual(decisions["multicar_merge_prominence"], "accepted")


if __name__ == "__main__":
    unittest.main()
